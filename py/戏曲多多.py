# -*- coding: utf-8 -*-
# 戏曲多多  TVBox / 影视仓 py 源
# 逆向自 无意.jar 的 com.github.catvod.spider.AppLY (siteKey = 戏曲多多)
#
# 接口(2026-10-13 实测全部可用):
#   POST https://fly.daoran.tv/API_ROP/<path>
#     Header: Content-Type: application/json;charset=utf-8
#             User-Agent:  okhttp/3.9.1
#             md5:         SkvyrWqK9QHTdCT12Rhxunjx+WwMTe9y4KwgeASFDhbYabRSPskR0Q==
#                          ^ 站点固定"密钥头"(原名 md5, 实为固定 base64 串, 非动态签名)
#     Body: JSON (UTF-8)
#     - page/setinf/get    分类剧种      {leastNum:"0", memberId:"yszyz", project:"lyhxcx", userId:"yszyz"}
#     - search/album/list  列表/搜索     {cur, free:"0", item:"o5", pageSize:"20", sect:[剧种]}
#                                      搜索时拆掉 sect 改传 keyword:"<关键词>"
#     - album/res/list     详情+剧集     {albumCode, cur:"1", project:"lyhxcx", pageSize:"999",
#                                       selectFlag:"0", userId:"yszyz"}
#     - play/get/playurl   取流          {item:"y9", nodeCode:"001000", project:"lyhxcx", px:"2",
#                                       resCode, userId:"92315ec6e58a45ba7f47fd143b3d7956"}
#
# 要点:
#   1) 响应码 code==10000000 表示成功; 列表/剧集数据都在 pb.dataList 里。
#   2) 封面前缀 https://ottphoto.daoran.tv/HD/ , 与接口返回的 img 拼接。
#   3) 播放返回明文 m3u8(1920x1080, 无 DRM、无 EXT-X-KEY), TS 分片为相对路径, 播放器可直连。
#   4) 全站只有一档清晰度(px=1 与 px=2 返回同一内容), 故只做单线路。
#   5) sect 传 [] 等于"全部剧种"; 传 ["all"] 无效(0 条), 故"全部"回调时用空数组。
#   6) playres 里的 width/height(1920x1080) 只是专辑标称值; ffprobe 实测片源真实分辨率随
#      上游母版而定(如《朝阳沟》杨红霞版=1920x1080@3.4Mbps, 康沙沙版=1280x720@1.9Mbps),
#      属片源本身差异, 不是源侧降级, 也无法在源里提升。
import json

try:
    import requests
except Exception:
    requests = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

HOST = "https://fly.daoran.tv/API_ROP/"
IMG_HOST = "https://ottphoto.daoran.tv/HD/"
UA = "okhttp/3.9.1"
MD5_KEY = "SkvyrWqK9QHTdCT12Rhxunjx+WwMTe9y4KwgeASFDhbYabRSPskR0Q=="
USER_ID = "92315ec6e58a45ba7f47fd143b3d7956"
EMPTY_SECT = "__all__"


class Spider(BaseSpider):
    def __init__(self):
        self.name = "戏曲多多"
        self._sess = None
        self._classes = None

    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if extend else {}
        except Exception:
            cfg = {}
        if isinstance(cfg, dict) and cfg.get("host"):
            global HOST
            HOST = str(cfg["host"]).rstrip("/") + "/"
        self._classes = None

    def getName(self):
        return self.name

    # ------------------------------------------------------------------ HTTP
    def _session(self):
        if self._sess is None:
            s = requests.Session()
            s.headers.update({
                "Content-Type": "application/json;charset=utf-8",
                "User-Agent": UA,
                "md5": MD5_KEY,
            })
            self._sess = s
        return self._sess

    def _post(self, path, body):
        """统一 POST: 返回 dict, 异常/失败返回 {}"""
        if requests is None:
            return {}
        try:
            r = self._session().post(
                HOST + path,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                timeout=15,
            )
            data = r.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _pb(j):
        return j.get("pb") if isinstance(j.get("pb"), dict) else {}

    # ------------------------------------------------------------------ 分类
    def _sects(self):
        if self._classes:
            return self._classes
        j = self._post("page/setinf/get", {
            "leastNum": "0", "memberId": "yszyz",
            "project": "lyhxcx", "userId": "yszyz",
        })
        classes = [{"type_id": EMPTY_SECT, "type_name": "全部"}]
        for it in (j.get("sects") or []):
            if not isinstance(it, dict):
                continue
            code = str(it.get("code") or "").strip()
            name = str(it.get("name") or "").strip()
            if code and name:
                classes.append({"type_id": code, "type_name": name})
        if len(classes) > 1:
            self._classes = classes
        return classes

    def homeContent(self, filter):
        items, _, _, _ = self._album("1", EMPTY_SECT)
        return {"class": self._sects(), "list": items}

    # ------------------------------------------------------------------ 列表
    def _album(self, pg, tid=None, keyword=None):
        """返回 (list, page, pagecount, total)"""
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        sect = [] if str(tid or "") in ("", EMPTY_SECT) else [str(tid)]
        body = {"cur": str(page), "free": "0", "item": "o5",
                "pageSize": "20", "sect": sect}
        if keyword:
            body["keyword"] = str(keyword)
        j = self._post("search/album/list", body)
        pb = self._pb(j)
        items = []
        for it in (pb.get("dataList") or []):
            if not isinstance(it, dict):
                continue
            code = str(it.get("code") or "").strip()
            if not code:
                continue
            items.append({
                "vod_id": code,
                "vod_name": str(it.get("name") or ""),
                "vod_pic": IMG_HOST + str(it.get("img") or ""),
                "vod_remarks": str(it.get("publishTime") or ""),
            })
        try:
            total_page = int(pb.get("totalPage") or 0)
        except Exception:
            total_page = 0
        try:
            total = int(pb.get("totalCount") or 0)
        except Exception:
            total = 0
        if total_page <= 0:
            # 接口没给分页信息时, 有数据就允许继续翻页
            total_page = page + 1 if items else page
        return items, page, total_page, total

    def categoryContent(self, tid, pg, filter, extend):
        items, page, pagecount, total = self._album(str(pg), str(tid))
        return {"page": page, "pagecount": pagecount,
                "limit": 20, "total": total, "list": items}

    def searchContent(self, key, quick=False, pg="1"):
        items, page, pagecount, total = self._album(str(pg), None, str(key))
        return {"page": page, "pagecount": pagecount,
                "limit": 20, "total": total, "list": items}

    # ------------------------------------------------------------------ 详情
    def detailContent(self, ids):
        code = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()
        if not code:
            return {"list": []}
        j = self._post("album/res/list", {
            "albumCode": code, "cur": "1", "project": "lyhxcx",
            "pageSize": "999", "selectFlag": "0", "userId": "yszyz",
        })
        album = j.get("album") if isinstance(j.get("album"), dict) else {}
        eps = [e for e in (self._pb(j).get("dataList") or []) if isinstance(e, dict)]
        if not album and not eps:
            return {"list": []}

        name = str(album.get("name") or code)
        multi = len(eps) > 1
        play = []
        for i, ep in enumerate(eps, 1):
            rc = str(ep.get("code") or "").strip()
            if not rc:
                continue
            play.append("%s$%s" % ("第%d集" % i if multi else name, rc))

        total_num = str(album.get("totalNum") or "").strip()
        remark = ("共%s集" % total_num) if (total_num and total_num != "0") else ""
        if not remark and len(eps) > 1:
            remark = "共%d集" % len(eps)

        vod = {
            "vod_id": code,
            "vod_name": name,
            "vod_pic": IMG_HOST + str(album.get("img") or ""),
            "vod_year": str(album.get("publishTime") or "")[:4],
            "vod_area": "",
            "vod_director": "",
            "vod_actor": str(album.get("artistName") or ""),
            "vod_content": str(album.get("des") or ""),
            "vod_remarks": remark,
            "vod_play_from": self.name,
            "vod_play_url": "#".join(play),
        }
        return {"list": [vod]}

    # ------------------------------------------------------------------ 播放
    def playerContent(self, flag, id, vipFlags=None):
        s = str(id or "").strip()
        if s.startswith("http"):
            return self._ok(s)
        j = self._post("play/get/playurl", {
            "item": "y9", "nodeCode": "001000", "project": "lyhxcx",
            "px": "2", "resCode": s, "userId": USER_ID,
        })
        res = j.get("playres") if isinstance(j.get("playres"), dict) else {}
        url = str(res.get("playurl") or "").strip()
        if not url:
            box = j.get("playUrls") if isinstance(j.get("playUrls"), dict) else {}
            for key in ("hd", "sd", "fd"):
                if box.get(key):
                    url = str(box[key]).strip()
                    break
        return self._ok(url)

    @staticmethod
    def _ok(url):
        return {
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": url,
            "header": {"User-Agent": UA, "Referer": "https://www.daoran.tv/"},
        }
