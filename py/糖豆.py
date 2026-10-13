# -*- coding: utf-8 -*-
# 糖豆┃广舞  TVBox / sky py 源
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
        # id 可能是: 纯 vid(来自选集列表) / 完整 http 直链
        url = str(id or "")
        if not url.startswith("http"):
            url = self._resolve(url)
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
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
        }

    def _fill_play(self, vod, vid):
        """二级列表: 本视频 + 往下 49 个(相关推荐), 共 50 项"""
        items = self._playlist(vid, vod.get("vod_name") or vid)
        eps = []
        for i, it in enumerate(items, 1):
            name = self._clean(it.get("vod_name") or it.get("vod_id"))
            if len(name) > 40:
                name = name[:40]
            eps.append("%d.%s$%s" % (i, name, it.get("vod_id")))
        vod["vod_play_from"] = self.name
        vod["vod_play_url"] = "#".join(eps)

    def _playlist(self, vid, cur_name):
        """本视频在最前, 后续取 share/recommend 相关视频补至 50 个"""
        vid = str(vid)
        out = [{"vod_id": vid, "vod_name": cur_name}]
        seen = {vid}
        for pn in range(1, 6):
            if len(out) >= 50:
                break
            data = self._get("%s/sample/share/recommend?page_num=%d&vid=%s" % (self.host, pn, vid))
            arr = data.get("data") if isinstance(data, dict) else None
            if not isinstance(arr, list) or not arr:
                break
            for it in arr:
                if not isinstance(it, dict):
                    continue
                v = str(it.get("vid") or "")
                if not v or v in seen:
                    continue
                seen.add(v)
                out.append({"vod_id": v, "vod_name": it.get("title") or v})
                if len(out) >= 50:
                    break
        # 相关视频不足时用首页推荐流补足
        if len(out) < 50:
            for page in range(1, 6):
                if len(out) >= 50:
                    break
                data = self._get("%s/mtangdou/home/feed?page=%d&num=30&uuid=%s" % (self.host, page, self.uuid))
                for it in self._vods(data.get("data") if isinstance(data, dict) else None):
                    if it["vod_id"] in seen:
                        continue
                    seen.add(it["vod_id"])
                    out.append(it)
                    if len(out) >= 50:
                        break
        return out[:50]

    def _resolve(self, vid):
        """vid -> mp4 直链: 优先 tv_api 多线路(hd/sd), 回退 video/play"""
        vid = str(vid or "").strip()
        if not vid:
            return ""
        try:
            url = ("%s/tv_api.php?mod=tv&ac=mp4&uuid=%s&version=7.1.2&client=3&channel_id=16&&time=%d&vid=%s"
                   % (self.host, self.uuid, int(time.time() * 1000), vid))
            data = self._get(url, {"Host": "aa.tangdou.com:12308"})
            datas = data.get("datas") if isinstance(data, dict) else None
            if isinstance(datas, dict):
                for key in ("hd", "sd"):
                    arr = datas.get(key)
                    if isinstance(arr, list):
                        for it in arr:
                            u = it.get("url") if isinstance(it, dict) else None
                            if u:
                                return u
        except Exception:
            pass
        try:
            data = self._get("%s/mtangdou/video/play?vid=%s&uuid=%s" % (self.host, vid, self.uuid))
            d = data.get("data") if isinstance(data, dict) else None
            if isinstance(d, dict):
                return d.get("play_url") or d.get("video_url") or ""
        except Exception:
            pass
        return ""

    def _clean(self, s):
        return str(s or "").replace("#", " ").replace("$", " ").replace("\r", " ").replace("\n", " ").strip()

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
        pic = it.get("cover") or it.get("img") or it.get("video_img") or it.get("pic") or ""
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
    print("home list:", len(hc["list"]))
    cc = s.categoryContent("1", "1", True, {"sort": "hot"})
    print("cate list:", len(cc["list"]))
    if cc["list"]:
        vid = cc["list"][0]["vod_id"]
        det = s.detailContent([vid])["list"][0]
        eps = det["vod_play_url"].split("#")
        print("detail:", det["vod_name"])
        print("播放列表共 %d 项 (from=%s)" % (len(eps), det["vod_play_from"]))
        for e in eps[:6]:
            print("   ", e.split("$")[0][:36], "->", e.split("$")[-1])
        print("   ...")
        print("最后一项:", eps[-1].split("$")[0][:36], "->", eps[-1].split("$")[-1])
        pc = s.playerContent("", eps[2].split("$")[-1], [])
        print("player(第3项):", pc["url"][:110])
        pc2 = s.playerContent("", eps[0].split("$")[-1], [])
        print("player(第1项=本视频):", pc2["url"][:110])
    sr = s.searchContent("广场舞", False, "1")
    print("search:", len(sr["list"]))
