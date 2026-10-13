# -*- coding: utf-8 -*-
# 糖豆┃广舞  TVBox / 影视仓 py 源
# 参考: 无意.jar -> com.github.catvod.spider.AppTd 的接口实现
# 接口(2026-10 实测可用):
#   首页/分类  https://api-h5.tangdou.com/mtangdou/home/feed?page=&num=30&uuid=[&type=][&sort=]
#   详情       https://api-h5.tangdou.com/mtangdou/video/play?vid=&uuid=
#   线路       https://api-h5.tangdou.com/tv_api.php?mod=tv&ac=mp4&uuid=&...&vid=
#   播放直链   详情/线路返回的 play_url / url (mp4, 需带 Referer: https://www.tangdou.com/)
# 注意: 糖豆官方搜索接口 mtangdou/search 已下线(服务端 500)，此处做了本地聚合降级
import json
import time
import urllib.parse
import urllib.request

try:
    import requests
except Exception:
    requests = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


class Spider(BaseSpider):
    def __init__(self):
        self.name = "糖豆┃广舞"
        self.host = "https://api-h5.tangdou.com"
        self.img_host = "https://bimg.tangdou.com"
        self.ua = ("Mozilla/5.0 (Linux; Android 7.1.2; ASUS_I003DD) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36")
        self.desc = "广场舞不只是简单的健身活动，更是当代中国一个独特的文化现象。它根植于普通人的生活，承载着许多人的健康追求和社交归属感。"
        self.headers = {
            "Connection": "keep-alive",
            "Referer": "https://www.tangdou.com/",
            "User-Agent": self.ua,
        }
        self.classes = [
            ("1", "广场舞"),
            ("2", "民族舞"),
            ("3", "现代舞"),
            ("4", "健身"),
            ("5", "双人舞"),
            ("6", "步法"),
            ("7", "气球"),
            ("8", "瑜伽"),
            ("9", "二人转"),
        ]
        self.uuid = self._gen_uuid()
        self.session = requests.Session() if requests else None
        if self.session is not None:
            try:
                self.session.headers.update(self.headers)
            except Exception:
                pass

    # ------------------------------------------------------------------ 生命周期
    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if extend else {}
        except Exception:
            cfg = {}
        if isinstance(cfg, dict) and cfg.get("host"):
            self.host = str(cfg["host"]).rstrip("/")
        self.uuid = self._gen_uuid()

    def getName(self):
        return self.name

    # ------------------------------------------------------------------ 首页
    def homeContent(self, filter):
        years = [{"n": "全部", "v": "0"}] + [{"n": str(y), "v": str(y)} for y in range(2026, 2019, -1)]
        sorts = [{"n": "最新", "v": "new"}, {"n": "最热", "v": "hot"}, {"n": "推荐", "v": "rec"}]
        filters = {}
        for tid, _ in self.classes:
            filters[tid] = [
                {"key": "year", "name": "年份", "value": years},
                {"key": "sort", "name": "排序", "value": sorts},
            ]
        return {
            "class": [{"type_id": t, "type_name": n} for t, n in self.classes],
            "filters": filters,
            "list": self._feed("1", "", {}),
        }

    # ------------------------------------------------------------------ 分类
    def categoryContent(self, tid, pg, filter, extend):
        items = self._feed(str(pg), tid, extend or {})
        return {
            "page": int(pg),
            # feed 为随机推荐流(每页固定16条), 只要有数据即允许继续翻页
            "pagecount": int(pg) + 1 if items else int(pg),
            "limit": 16,
            "total": 999999,
            "list": items,
        }

    # ------------------------------------------------------------------ 详情
    def detailContent(self, ids):
        vid = str(ids[0])
        vod = self._video(vid)
        if not vod:
            return {"list": []}
        self._fill_play(vod, vid)
        return {"list": [vod]}

    # ------------------------------------------------------------------ 搜索
    def searchContent(self, key, quick, pg="1"):
        items = self._search(str(key), str(pg))
        return {
            "page": int(pg),
            "pagecount": int(pg) + 1 if items else int(pg),
            "limit": 30,
            "total": 999999,
            "list": items,
        }

    # ------------------------------------------------------------------ 播放
    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "playUrl": "",
            "url": id,
            "header": dict(self.headers),
        }

    # ================================================================== 内部实现
    def _gen_uuid(self):
        ms = int(time.time() * 1000)
        return "%d_%d" % (ms, ms % 100000)

    def _feed(self, pg, tid, extend):
        url = "%s/mtangdou/home/feed?page=%s&num=30&uuid=%s" % (self.host, pg, self.uuid)
        if tid and str(tid) != "0":
            url += "&type=" + str(tid)
        extend = extend or {}
        sort = str(extend.get("sort") or "")
        if sort in ("new", "hot", "rec"):
            url += "&sort=" + sort
        year = str(extend.get("year") or "")
        if year and year != "0":
            url += "&year=" + year
        data = self._get(url)
        return self._vods(data.get("data") if isinstance(data, dict) else None)

    def _video(self, vid):
        data = self._get("%s/mtangdou/video/play?vid=%s&uuid=%s" % (self.host, vid, self.uuid))
        d = data.get("data") if isinstance(data, dict) else None
        if not isinstance(d, dict):
            return {}
        pic = self._pic(d)
        name = d.get("name") or ""
        return {
            "vod_id": vid,
            "vod_name": d.get("title") or vid,
            "vod_pic": pic,
            "vod_actor": name,
            "vod_director": name,
            "type_name": "广场舞",
            "vod_year": "",
            "vod_area": "中国",
            "vod_remarks": self._dur(d.get("duration")),
            "vod_content": self.desc,
            "vod_play_from": self.name,
            "vod_play_url": "",
            "_fallback": d.get("play_url") or d.get("video_url") or "",
        }

    def _fill_play(self, vod, vid):
        url = ("%s/tv_api.php?mod=tv&ac=mp4&uuid=%s&version=7.1.2&client=3&channel_id=16&&time=%d&vid=%s"
               % (self.host, self.uuid, int(time.time() * 1000), vid))
        data = self._get(url, {"Host": "aa.tangdou.com:12308"})
        datas = data.get("datas") if isinstance(data, dict) else None
        froms, urls = [], []
        if isinstance(datas, dict):
            for key, label in (("hd", "高清"), ("sd", "标清")):
                arr = datas.get(key)
                if not isinstance(arr, list):
                    continue
                lines = []
                for i, it in enumerate(arr, 1):
                    u = it.get("url") if isinstance(it, dict) else None
                    if u:
                        lines.append("线路%d$%s" % (i, u))
                if lines:
                    froms.append(label)
                    urls.append("#".join(lines))
        if not froms:
            fb = vod.pop("_fallback", "")
            if fb:
                froms.append(self.name)
                urls.append("播放$" + fb)
        else:
            vod.pop("_fallback", None)
        vad = "$$$".join(froms) if froms else self.name
        vu = "$$$".join(urls) if urls else ""
        vod["vod_play_from"] = vad
        vod["vod_play_url"] = vu

    def _search(self, key, pg):
        # 1) 官方搜索接口(糖豆已下线, 保留兼容: 一旦恢复自动生效)
        try:
            url = "%s/mtangdou/search?word=%s&page=%s&num=30&uuid=%s" % (
                self.host, urllib.parse.quote(key), pg, self.uuid)
            data = self._get(url)
            if isinstance(data, dict) and data.get("code") == 0:
                items = self._vods(data.get("data"))
                if items:
                    return items
        except Exception:
            pass
        # 2) 降级: 聚合首页 + 全部分类首页, 本地关键词过滤
        if pg != "1":
            return []
        return self._local_search(key)

    def _local_search(self, key):
        key = (key or "").strip()
        if not key:
            return []
        pool = []
        for t in [""] + [c[0] for c in self.classes]:
            try:
                url = "%s/mtangdou/home/feed?page=1&num=30&uuid=%s" % (self.host, self.uuid)
                if t:
                    url += "&type=" + t
                data = self._get(url)
                pool += self._vods(data.get("data") if isinstance(data, dict) else None)
            except Exception:
                continue
        seen, out = set(), []
        for it in pool:
            vid = it.get("vod_id")
            if vid in seen:
                continue
            seen.add(vid)
            if key in (it.get("vod_name") or "") or key in (it.get("vod_remarks") or ""):
                out.append(it)
        return out

    def _vods(self, arr):
        out = []
        if not isinstance(arr, list):
            return out
        for it in arr:
            if not isinstance(it, dict):
                continue
            vid = str(it.get("vid") or "")
            if not vid:
                continue
            name = it.get("name") or it.get("teacher") or it.get("author") or ""
            out.append({
                "vod_id": vid,
                "vod_name": it.get("title") or name or vid,
                "vod_pic": self._pic(it),
                "vod_remarks": name,
            })
        return out

    def _pic(self, it):
        pic = it.get("cover") or it.get("img") or it.get("video_img") or ""
        if pic and not str(pic).startswith("http"):
            pic = self.img_host + str(pic)
        return pic

    def _dur(self, x):
        try:
            s = int(float(x))
            return "%d:%02d" % (s // 60, s % 60)
        except Exception:
            return ""

    def _get(self, url, extra=None):
        headers = dict(self.headers)
        if extra:
            headers.update(extra)
        if self.session is not None:
            try:
                r = self.session.get(url, headers=headers, timeout=15)
                if r.status_code < 400:
                    txt = r.text
                    if txt:
                        return json.loads(txt)
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8", "ignore"))
        except Exception:
            return {}


if __name__ == "__main__":
    s = Spider()
    s.init()
    print("name:", s.getName())
    hc = s.homeContent(True)
    print("classes:", [c["type_name"] for c in hc["class"]])
    print("home list:", len(hc["list"]), hc["list"][0] if hc["list"] else None)
    cc = s.categoryContent("1", "1", True, {"sort": "hot"})
    print("cate list:", len(cc["list"]))
    if cc["list"]:
        vid = cc["list"][0]["vod_id"]
        det = s.detailContent([vid])
        print("detail:", json.dumps(det["list"][0], ensure_ascii=False)[:400])
    sr = s.searchContent("广场舞", False, "1")
    print("search:", len(sr["list"]))
