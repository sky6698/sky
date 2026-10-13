# -*- coding: utf-8 -*-
# 糖豆┃广舞  TVBox / 影视仓 py 源
# 接口(2026-10 实测可用):
#   首页/分类  https://api-h5.tangdou.com/mtangdou/home/feed?page=&num=30&uuid=[&type=][&sort=][&year=]
#   详情       https://api-h5.tangdou.com/mtangdou/video/play?vid=&uuid=      -> 720P 官方线路
#   分享详情   https://api-h5.tangdou.com/sample/share/main?vid=               -> 540P 分享线路 + head_t(片头秒数)
#   线路/清晰度 https://api-h5.tangdou.com/tv_api.php?mod=tv&ac=mp4&uuid=&...&vid=  -> hd(1080P)/sd(720P) 多CDN
#   相关推荐   https://api-h5.tangdou.com/sample/share/recommend?page_num=&vid=
# 注意:
#   1) 糖豆官方搜索接口 mtangdou/search 已下线(服务端 500)，此处做了本地聚合降级
#   2) tv_api 有按 IP 的调用配额, 超限返回 {"code":"1","msg":"试看结束,请购买会员"},
#      此时自动降级为 video/play + share/main 两条常驻线路, 不影响观看
#   3) 视频前 6 秒为糖豆平台自带片头(head_t=6, 老片为 0), 需在播放器设置里"跳过片头"
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
        # 详情 -> 播放 之间的小缓存, 避免重复请求
        self._cache = {}
        # tv_api 配额失败后的冷却截止时间戳
        self._tv_down_until = 0.0

    # ------------------------------------------------------------------ 生命周期
    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if extend else {}
        except Exception:
            cfg = {}
        if isinstance(cfg, dict) and cfg.get("host"):
            self.host = str(cfg["host"]).rstrip("/")
        self.uuid = self._gen_uuid()
        self._cache = {}
        self._tv_down_until = 0.0

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
        vp = self._video_play(vid)
        if not vp:
            return {"list": []}
        sh = self._share_main(vid)
        vod = self._video(vid, vp, sh)
        lines = self._lines(vid, vp, sh)
        items = self._playlist(vid, vod.get("vod_name") or vid)
        froms, urls = [], []
        for ln in lines:
            eps = []
            for i, it in enumerate(items, 1):
                nm = self._clean(it.get("vod_name") or it.get("vod_id"))
                if len(nm) > 40:
                    nm = nm[:40]
                eps.append("%d.%s$%s@%s" % (i, nm, ln["key"], it.get("vod_id")))
            froms.append(ln["label"])
            urls.append("#".join(eps))
        vod["vod_play_from"] = "$$$".join(froms) if froms else self.name
        vod["vod_play_url"] = "$$$".join(urls) if urls else ""
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
        # id 三种形态: 完整 http 直链 / "线路key@vid" / 纯 vid
        s = str(id or "")
        if s.startswith("http"):
            return self._ok(s)
        key, vid = "", s
        if "@" in s:
            key, vid = s.rsplit("@", 1)
        url = self._resolve(vid, key)
        return self._ok(url)

    @staticmethod
    def _ok(url):
        return {"parse": 0, "playUrl": "", "url": url,
                "header": {"User-Agent": Spider._UA, "Referer": "https://www.tangdou.com/"}}

    _UA = ("Mozilla/5.0 (Linux; Android 7.1.2; ASUS_I003DD) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36")

    # ================================================================== 线路 / 清晰度
    def _lines(self, vid, vp, sh):
        """返回可选线路列表 [{key,label,url}], 按清晰度从高到低"""
        out, seen = [], set()

        def add(key, label, url):
            if url and key not in seen:
                seen.add(key)
                out.append({"key": key, "label": label, "url": url})

        # 1) tv_api: hd(1080P) / sd(720P), 多 CDN (可能额度耗尽)
        datas = self._tv_datas(vid)
        for k in ("hd", "sd"):
            for it in (datas.get(k) or []):
                if not isinstance(it, dict):
                    continue
                u = it.get("url")
                if not u:
                    continue
                cdn = str(it.get("cdn_source") or k)
                tier = self._tier(it.get("define"), k)
                add("%s_%s" % (tier, cdn),
                    "%s·%s" % (self._tier_name(tier), self._cdn_name(cdn)), u)
        # 2) 常驻: video/play 官方 720P
        add("q720_official", "720P·官方", (vp or {}).get("play_url"))
        # 3) 常驻: share/main 分享 540P
        add("q540_share", "540P·分享", (sh or {}).get("video_url"))
        return out

    def _tv_datas(self, vid):
        """tv_api 多线路数据; 额度耗尽或被限时返回 {} 并进入冷却"""
        key = "tv:" + str(vid)
        if key in self._cache:
            return self._cache[key]
        if time.time() < self._tv_down_until:
            return {}
        datas = {}
        try:
            url = ("%s/tv_api.php?mod=tv&ac=mp4&uuid=%s&version=7.1.2&client=3"
                   "&channel_id=16&&time=%d&vid=%s"
                   % (self.host, self.uuid, int(time.time() * 1000), vid))
            data = self._get(url, {"Host": "aa.tangdou.com:12308"})
            if isinstance(data, dict) and isinstance(data.get("datas"), dict):
                datas = data["datas"]
        except Exception:
            datas = {}
        if datas:
            self._cache[key] = datas
        else:
            # 配额耗尽(code=1 试看结束) 或异常: 冷却 20 分钟再试
            self._tv_down_until = time.time() + 1200
        return datas

    def _resolve(self, vid, key):
        """vid + 线路key -> mp4 直链; 线路缺失时逐级降级"""
        vid = str(vid or "").strip()
        if not vid:
            return ""
        key = str(key or "")

        def official():
            return (self._video_play(vid) or {}).get("play_url") or ""

        def share():
            return (self._share_main(vid) or {}).get("video_url") or ""

        def pick(box=None, cdn=None):
            """1.指定档位+指定CDN  2.指定档位+任意CDN  3.任意档位"""
            datas = self._tv_datas(vid)
            order = ("hd", "sd") if box is None else (box,) + tuple(x for x in ("hd", "sd") if x != box)

            def scan(only_box, only_cdn):
                for k in ([only_box] if only_box else order):
                    for it in (datas.get(k) or []):
                        if not isinstance(it, dict) or not it.get("url"):
                            continue
                        if only_cdn and str(it.get("cdn_source")) != only_cdn:
                            continue
                        return it["url"]
                return ""

            if cdn and box:
                u = scan(box, cdn) or scan(box, None)
                if u:
                    return u
            return scan(None, None)

        if key == "q540_share":
            return share() or official() or pick()
        if key == "q720_official":
            return official() or share() or pick()
        if key.startswith("q1080_") or key.startswith("q720_"):
            tier, _, cdn = key.partition("_")
            box = "hd" if tier == "q1080" else "sd"
            return pick(box, cdn or None) or official() or share()
        # 纯 vid / 未指定: 1080P -> 720P -> 官方 -> 分享
        return pick() or official() or share()

    def _tier(self, define, box):
        """define: 3=1080P 2=720P 1=540P; 缺失时按 hd/sd 兜底"""
        try:
            d = int(define)
        except Exception:
            d = 0
        if d >= 3:
            return "q1080"
        if d == 2:
            return "q720"
        if d == 1:
            return "q540"
        return "q1080" if box == "hd" else "q720"

    @staticmethod
    def _tier_name(tier):
        return {"q1080": "1080P", "q720": "720P", "q540": "540P"}.get(tier, tier)

    @staticmethod
    def _cdn_name(cdn):
        return {"ucloud": "UC", "qiniu": "七牛", "official": "官方",
                "share": "分享"}.get(str(cdn), str(cdn))

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

    def _video_play(self, vid):
        key = "vp:" + str(vid)
        if key in self._cache:
            return self._cache[key]
        data = self._get("%s/mtangdou/video/play?vid=%s&uuid=%s" % (self.host, vid, self.uuid))
        d = data.get("data") if isinstance(data, dict) else None
        d = d if isinstance(d, dict) else {}
        self._cache[key] = d
        return d

    def _share_main(self, vid):
        key = "sh:" + str(vid)
        if key in self._cache:
            return self._cache[key]
        data = self._get("%s/sample/share/main?vid=%s" % (self.host, vid))
        d = data.get("data") if isinstance(data, dict) else None
        d = d if isinstance(d, dict) else {}
        self._cache[key] = d
        return d

    def _video(self, vid, vp, sh):
        pic = self._pic(vp)
        if not pic and sh:
            pic = sh.get("pic") or ""
        name = vp.get("name") or sh.get("user_name") or ""
        head = self._int(sh.get("head_t"))
        content = self.desc
        if head > 0:
            content += "\n\n提示：本片前 %d 秒为糖豆平台自带片头，可在播放器「跳过片头」中设为 %d 秒跳过。" % (head, head)
        return {
            "vod_id": vid,
            "vod_name": vp.get("title") or sh.get("title") or vid,
            "vod_pic": pic,
            "vod_actor": name,
            "vod_director": name,
            "type_name": "广场舞",
            "vod_year": "",
            "vod_area": "中国",
            "vod_remarks": self._dur(vp.get("duration") or sh.get("duration")),
            "vod_content": content,
            "vod_play_from": self.name,
            "vod_play_url": "",
        }

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

    def _clean(self, s):
        return str(s or "").replace("#", " ").replace("$", " ").replace("@", " ").replace("\r", " ").replace("\n", " ").strip()

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

    @staticmethod
    def _int(x):
        try:
            return int(float(x))
        except Exception:
            return 0

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
        froms = det["vod_play_from"].split("$$$")
        groups = det["vod_play_url"].split("$$$")
        print("detail:", det["vod_name"], "|", det["vod_remarks"])
        print("线路 %d 条: %s" % (len(froms), froms))
        for i, g in enumerate(groups):
            eps = g.split("#")
            print("   [%s] 集数=%d 首项=%s" % (froms[i] if i < len(froms) else "?", len(eps),
                                             eps[0].split("$")[0][:24]))
        for i, ln in enumerate(froms):
            pid = groups[i].split("#")[2].split("$")[-1]
            pc = s.playerContent(ln, pid, [])
            print("   %-14s -> %s" % (ln, pc["url"][:100] if pc["url"].startswith("http") else "FAIL " + pc["url"][:40]))
    sr = s.searchContent("广场舞", False, "1")
    print("search:", len(sr["list"]))
