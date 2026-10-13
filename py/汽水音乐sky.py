# -*- coding: utf-8 -*-
# 汽水音乐  TVBox / 影视仓 py 源
# 站点: 字节「汽水音乐」Web 接口 https://api.qishui.com
#
# 端点(2026-10-13 全部实测可用, 无需登录):
#   POST /luna/feed/mode                       听歌模式墙  feed_mode_block[].feed_mode[].entity.feed_scene_mode
#   POST /luna/discover                        发现页      blocks[].inner_block[].resources[]
#   POST /luna/discover/mix                    发现页补充混合流
#   GET  /luna/charts/<chart_id>               榜单        chart.track_ranks[]
#   POST /luna/feed/radio/tracks               电台曲目    items[]  {radio_id, flow_type, full_media,...}
#   POST /luna/playlist/detail                 歌单曲目    media_resources[].entity.track_wrapper.track
#   POST /luna/search/track?device_platform=web        搜歌   result_groups[tracks].data[]
#   POST /luna/search/playlist?device_platform=web     搜歌单 result_groups[playlists].data[]
#   POST /luna/search/listen_video?device_platform=web 听抖音 result_groups[listen_video].data[]
#   GET  /luna/h5/seo_track?track_id=&device_platform=web   取流  track_player.video_model.video_list[]
#
# 取流要点:
#   - video_list 每项 = {video_meta:{quality,bitrate,codec_type,size,...}, main_url, backup_url}。
#     quality 取值 medium(≈65k) / higher(≈129k) / highest(≈257k)。
#   - ★档位数量由歌曲本身决定(常见 1~3 档); 匿名最高到 highest(~257kbps), 拿不到无损档。
#   - 带 encrypt_info 的档位是加密流, 跳过不用; 实测匿名返回的各档均无 encrypt_info。
#   - 备用源: track_player.url_player_info 是 vod-luna 的 GetPlayInfo 地址,
#     其 PlayInfoList 与 video_list 同源同档, 仅在 video_list 为空时兜底。
#
# 听抖音要点:
#   - ★必须带 device_platform=web, 否则一律 0 条。
#   - ★搜索词用「推荐 / 音乐」等有结果; 用「热门视频」返回 0 条(踩过的坑)。
#   - 播放: aweme.snssdk.com/aweme/v1/play/?video_id=<vid>&ratio=1080p&line=0
#     (HEAD 200 video/mp4; 注意用 vid(字符串) 不是 video_id(数字))。
#
# 格式约定: vod_play_from 用 $$$ 分隔线路; vod_play_url 同序;
#           集内 # 分隔; 每集 title$id 用 $ 分隔。
import base64
import json
import urllib.parse

try:
    import requests
except Exception:
    requests = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

API = "https://api.qishui.com"
UA = ("Mozilla/5.0 (Linux; Android 12; TVBox) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
ICON = ("https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/23/19/5a/"
        "23195ac8-3fbf-d33b-16ed-20854f9afd35/"
        "AppIcon-0-0-1x_U007epad-0-1-0-85-220.png/512x512bb.jpg")

# 热歌榜 / 新歌榜(实测可用)
CHARTS = [("热歌榜", "7036274230471712007"), ("新歌榜", "7060812597884869927")]
# 怀旧电台(「熟悉模式」用)
NOSTALGIA_RADIO = "7408841207276748809"
# 听抖音分类: (显示名, 搜索关键词)。★关键词用分类名本身; 不要用「热门视频」。
VIDEO_CATS = [
    ("推荐", "推荐"), ("音乐", "音乐"), ("助眠", "助眠"), ("脱口秀", "脱口秀"),
    ("相声", "相声"), ("影视解说", "影视解说"), ("历史", "历史"), ("科普", "科普"),
    ("财经", "财经"), ("职场", "职场"), ("悬疑", "悬疑"), ("小说", "小说"),
    ("爽文", "爽文"), ("现言", "现言"), ("穿越", "穿越"), ("重生", "重生"),
    ("脑洞", "脑洞"), ("男频", "男频"), ("女频", "女频"), ("社会时政", "社会时政"),
]
# 模式墙排序(接口返回顺序不稳定, 按此表归一; 表外模式排最后)
MODE_ORDER = [
    "默认模式", "熟悉模式", "新鲜模式", "图书馆", "专注模式", "摸鱼", "深夜emo", "dj模式", "助眠模式",
    "动感健身", "抖音漫游", "洗澡", "chill放松", "快乐时光", "电音", "好运", "粤语", "通勤必听",
    "失恋必听", "躺平", "欧美", "打扫", "国风", "打游戏", "驾车", "说唱", "沉浸0.8x", "夜晚",
    "治愈", "轻音乐", "小酒馆", "ktv必点", "起床", "浪漫情歌", "摇滚", "r&b", "佛系时间",
    "怀旧老歌", "民谣", "甜美女声", "k-pop", "日语", "旅行", "儿歌", "雨天", "海边", "乡村", "古典",
]


class Spider(BaseSpider):
    def __init__(self):
        self._sess = None

    def init(self, extend=""):
        try:
            self._cfg = json.loads(extend) if (isinstance(extend, str) and extend.strip()) else extend
        except Exception:
            self._cfg = {}
        if not isinstance(self._cfg, dict):
            self._cfg = {}

    def getName(self):
        return "汽水音乐"

    # ------------------------------------------------------------------ HTTP
    def _session(self):
        if self._sess is None:
            s = requests.Session()
            s.headers.update({
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://music.douyin.com/",
            })
            self._sess = s
        return self._sess

    def _req(self, path, body=None, query=None):
        """统一请求: GET(query) / POST(body) 都返回 dict, 失败返回 {}"""
        if requests is None:
            return {}
        url = API + path
        try:
            if body is None:
                r = self._session().get(url, params=query or None, timeout=18)
            else:
                r = self._session().post(
                    url, params=query or None,
                    data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json; charset=utf-8"}, timeout=18)
            data = r.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------- 字段工具
    @staticmethod
    def _first(value):
        return value[0] if isinstance(value, list) and value else value

    @classmethod
    def _img(cls, image):
        """封面: urls 里形如 https://p3-luna.douyinpic.com/img/ 需拼 uri + 模板后缀"""
        if not isinstance(image, dict):
            return ""
        uri = str(image.get("uri") or "")
        url = str(cls._first(image.get("urls")) or "")
        if url and url.rstrip("/").endswith("/img"):
            if not uri:
                return ""
            full = url.rstrip("/") + "/" + uri.lstrip("/")
            tpl = str(image.get("template_prefix") or "")
            return full + ("~" + tpl + "-ori.image" if tpl else "")
        return url or uri

    @staticmethod
    def _pack(kind, value):
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return kind + ":" + base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    @staticmethod
    def _unpack(value, kind):
        text = str(value or "")
        prefix = kind + ":"
        if not text.startswith(prefix):
            return None
        raw = text[len(prefix):]
        try:
            return json.loads(base64.urlsafe_b64decode((raw + "=" * (-len(raw) % 4)).encode()).decode())
        except Exception:
            return None

    @staticmethod
    def _result(items, page=1, more=False, size=20):
        page = max(1, int(page or 1))
        return {
            "list": items, "page": page,
            "pagecount": page + 1 if more else page,
            "limit": size,
            "total": (page - 1) * size + len(items) + (size if more else 0),
        }

    @staticmethod
    def _extend(extend, key, default=""):
        value = extend.get(key, default) if isinstance(extend, dict) else default
        if isinstance(value, list):
            value = value[0] if value else default
        if isinstance(value, dict):
            value = value.get("v") or value.get("value") or default
        return str(value if value not in (None, "") else default)

    @staticmethod
    def _track(obj):
        """从各种嵌套结构里抠出 track 对象"""
        if not isinstance(obj, dict):
            return None
        if obj.get("id") and (obj.get("name") or obj.get("title")):
            return obj
        for path in (("track",), ("track_wrapper", "track"),
                     ("entity", "track_wrapper", "track"), ("entity", "track")):
            value = obj
            for key in path:
                value = value.get(key) if isinstance(value, dict) else None
            if isinstance(value, dict) and value.get("id"):
                return value
        return None

    @classmethod
    def _card(cls, track):
        """track → TVBox 卡片"""
        if not isinstance(track, dict) or not track.get("id"):
            return None
        artists = " / ".join(str(a.get("name") or "") for a in (track.get("artists") or [])
                             if isinstance(a, dict) and a.get("name"))
        album = track.get("album") if isinstance(track.get("album"), dict) else {}
        remark = artists or str(album.get("name") or "汽水音乐")
        return {
            "vod_id": cls._pack("t", str(track["id"])),
            "vod_name": str(track.get("name") or "未知歌曲"),
            "vod_pic": cls._img(album.get("url_cover") or track.get("url_cover") or {}),
            "vod_remarks": remark[:60],
        }

    # ------------------------------------------------------------------ 分类
    def homeContent(self, filter):
        classes = [
            {"type_id": "mode", "type_name": "听歌模式"},
            {"type_id": "discover", "type_name": "发现"},
            {"type_id": "chart", "type_name": "榜单"},
            {"type_id": "listen_video", "type_name": "听抖音"},
        ]
        filters = {
            "listen_video": [{"key": "cate", "name": "分类",
                              "value": [{"n": n, "v": v} for n, v in VIDEO_CATS]}],
        }
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        try:
            return self._modes(1)
        except Exception:
            return self._result([], 1)

    def categoryContent(self, tid, pg, filter, extend):
        page = max(1, int(pg or 1))
        try:
            if str(tid) == "mode":
                return self._modes(page)
            if str(tid) == "discover":
                return self._discover(page)
            if str(tid) == "chart":
                return self._charts(page)
            return self._listen(self._extend(extend, "cate", "推荐"), page)
        except Exception:
            return self._result([], page)

    def _modes(self, page):
        """听歌模式墙(3 个基础偏好 + 接口返回的场景模式)"""
        data = self._req("/luna/feed/mode", {"ab_param": "", "feed_extra": None})
        modes = [
            {"id": "default", "name": "默认模式", "kind": "preference"},
            {"id": "familiar", "name": "熟悉模式", "kind": "preference"},
            {"id": "fresh", "name": "新鲜模式", "kind": "preference"},
        ]
        for group in (data.get("feed_mode_block") or []):
            for mode in (group.get("feed_mode") or []):
                scene = ((mode.get("entity") or {}).get("feed_scene_mode") or {})
                sid = str(scene.get("scene_mode_id") or mode.get("text") or "")
                if sid:
                    modes.append({"id": sid, "name": str(mode.get("text") or "听歌模式"), "kind": "scene"})
        cards, seen = [], set()
        for info in modes:
            key = info["name"].lower().replace(" ", "")
            if not info["id"] or key in seen:
                continue
            seen.add(key)
            cards.append({"vod_id": self._pack("m", info), "vod_name": info["name"],
                          "vod_pic": ICON, "vod_remarks": "听歌模式"})
        order = {n.lower().replace(" ", ""): i for i, n in enumerate(MODE_ORDER)}
        cards.sort(key=lambda x: order.get(x["vod_name"].lower().replace(" ", ""), len(order)))
        return self._result(cards, page, False, max(1, len(cards)))

    def _discover(self, page):
        """发现页: blocks + 混合流"""
        data = self._req("/luna/discover", {
            "ab_param": "", "selected_boost": None, "playlist_mix_param": None,
            "feed_discover_extra": None, "first_request": True})
        blocks = list(data.get("blocks") or [])
        for _ in range(2):
            mixed = self._req("/luna/discover/mix", {
                "block_type": "discover_playlist_mix", "sub_channel_id": 0,
                "latest_douyin_liked_playlist_show_ts": None, "feed_discover_extra": {},
                "cursor": None, "count": 50, "session_id": None, "ab_param": ""})
            blocks.append({"inner_block": mixed.get("inner_block") or [], "title": "发现"})
        cards, seen = [], set()
        for block in blocks:
            inners = block.get("inner_block") or ([block] if block.get("resources") else [])
            for inner in inners:
                for res in (inner.get("resources") or []):
                    kind = str(res.get("type") or "radio")
                    rid = str(res.get("resource_id") or "")
                    if not rid or (kind, rid) in seen:
                        continue
                    seen.add((kind, rid))
                    style = res.get("style") if isinstance(res.get("style"), dict) else {}
                    entity = res.get("entity") if isinstance(res.get("entity"), dict) else {}
                    cover = style.get("cover_url") or self._first(style.get("cover_url_list")) or {}
                    if not cover and isinstance(entity.get("playlist"), dict):
                        cover = entity["playlist"].get("url_cover") or {}
                    name = str(style.get("title") or inner.get("title") or "发现")
                    desc = str(style.get("desc") or block.get("title") or "发现")
                    cards.append({
                        "vod_id": self._pack("c", {"id": rid, "kind": kind, "name": name, "desc": desc,
                                                   "pic": self._img(cover)}),
                        "vod_name": name, "vod_pic": self._img(cover), "vod_remarks": desc[:60]})
        return self._result(cards, page, False, max(1, len(cards)))

    def _charts(self, page):
        return self._result([
            {"vod_id": self._pack("c", {"id": cid, "kind": "chart", "name": name,
                                        "desc": "榜单", "pic": ICON}),
             "vod_name": name, "vod_pic": ICON, "vod_remarks": "榜单"}
            for name, cid in CHARTS], page, False, len(CHARTS))

    def _listen(self, cate, page):
        """听抖音视频流"""
        name = next((n for n, v in VIDEO_CATS if v == str(cate)), str(cate) or "推荐")
        keyword = name or "推荐"
        payload = {
            "search_type": "listen_video", "q": keyword,
            "cursor": None if page == 1 else str((page - 1) * 20),
            "search_id": keyword, "search_method": "input",
            "search_scene": "search_result", "scene_name": "listen_video",
        }
        data = self._req("/luna/search/listen_video", payload, {"device_platform": "web"})
        group = next((g for g in (data.get("result_groups") or []) if g.get("id") == "listen_video"), {})
        cards = []
        for item in (group.get("data") or []):
            video = ((item.get("entity") or {}).get("video") or {})
            vid = str(video.get("vid") or "")
            if not vid:
                continue
            title = str(video.get("title") or video.get("description") or "听抖音")
            cover = self._img(video.get("cover_url") or video.get("image_url") or {})
            dur = int(video.get("duration") or 0) // 1000
            cards.append({
                "vod_id": self._pack("v", {"vid": vid, "name": title, "pic": cover, "dur": dur}),
                "vod_name": title, "vod_pic": cover,
                "vod_remarks": "%d:%02d" % (dur // 60, dur % 60) if dur else "听抖音"})
        return self._result(cards, page, bool(group.get("has_more")), 20)

    # ------------------------------------------------------------------ 搜索
    def searchContent(self, key, quick=False, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick=False, pg="1"):
        page = max(1, int(pg or 1))
        keyword = str(key or "").strip()
        if not keyword:
            return self._result([], 1)
        payload = {
            "search_type": "track", "q": keyword,
            "cursor": None if page == 1 else str((page - 1) * 20),
            "search_id": keyword, "search_method": "input", "search_scene": "search_result",
        }
        try:
            data = self._req("/luna/search/track", payload, {"device_platform": "web"})
            group = next((g for g in (data.get("result_groups") or []) if g.get("id") == "tracks"), {})
            cards = [c for c in (self._card(self._track(x)) for x in (group.get("data") or [])) if c]
            return self._result(cards, page, bool(group.get("has_more")), 20)
        except Exception:
            return self._result([], page)

    # ------------------------------------------------------------------ 详情
    def detailContent(self, ids):
        value = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
        try:
            video = self._unpack(value, "v")
            if video:
                return {"list": [self._video_detail(video)], "parse": 0, "jx": 0}
            collection = self._unpack(value, "c")
            if collection:
                return {"list": [self._collection_detail(collection)], "parse": 0, "jx": 0}
            mode = self._unpack(value, "m")
            if mode:
                return {"list": [self._collection_detail(mode)], "parse": 0, "jx": 0}
            track = self._unpack(value, "t")
            return {"list": [self._track_detail(track or value)], "parse": 0, "jx": 0}
        except Exception:
            return {"list": [{"vod_id": value, "vod_name": "汽水音乐", "vod_play_from": "汽水音乐",
                              "vod_play_url": "播放$a:" + value + ":auto"}], "parse": 0, "jx": 0}

    def _seo(self, track_id):
        return self._req("/luna/h5/seo_track", None,
                         {"track_id": str(track_id), "device_platform": "web"})

    def _req_url(self, url):
        if requests is None:
            return {}
        try:
            return self._session().get(url, timeout=18).json()
        except Exception:
            return {}

    # --------------------------------------------------- VIP/试听歌曲替代
    # 汽水对会员曲只放「试听片段」: video_list 只 1 档, 且正片短。判定依据
    # (实测 2026-10-13): seo_track.track.label_info.only_vip_playable = true
    # 或 track.audition_info 非空。命中后改走 yx520 的完整音源兜底:
    #   ① 酷我 kwyy → 返回 kuwo mp3 直链(完整, ~10MB, audio/mpeg)
    #   ② 抖音 dyyy → 返回 douyin audio_mp4 直链(完整, ~7MB)
    # 两个都是第三方免费接口, 任一可用即可; 全挂则回落官方试听档, 不阻断播放。
    @staticmethod
    def _is_vip(data):
        track = Spider._track((data or {}).get("seo_track") or {}) or {}
        label = track.get("label_info") if isinstance(track.get("label_info"), dict) else {}
        if label.get("only_vip_playable"):
            return True
        return bool(track.get("audition_info"))

    def _alt_url(self, name):
        """VIP 替代: 酷我(kwyy) 优先 → 抖音(dyyy) 兜底; 取不到返回 ''"""
        name = str(name or "").strip()
        if not name:
            return ""
        q = urllib.parse.quote(name)
        try:
            j = self._req_url("http://www.yx520.ltd/API/kwyy/api.php?msg=%s&a=10&n=1" % q)
            if str(j.get("code")) == "200" and j.get("url"):
                return str(j["url"])
        except Exception:
            pass
        try:
            j = self._req_url("http://www.yx520.ltd/API/dyyy/api.php?msg=%s" % q)
            items = j.get("data") or []
            if items:
                hit = next((x for x in items if name in str(x.get("title") or "")), items[0])
                if hit.get("url"):
                    return str(hit["url"])
        except Exception:
            pass
        return ""

    @staticmethod
    def _label(quality, bitrate, index):
        q = str(quality or "").lower()
        name = {"lossless": "无损", "highest": "极高", "higher": "较高",
                "medium": "标准", "low": "省流"}.get(q)
        kbps = max(0, int(bitrate or 0) // 1000)
        if name:
            return "%s音质(%dK)" % (name, kbps) if kbps else name + "音质"
        return "%dKbps" % kbps if kbps else "音质%d" % (index + 1)

    def _streams(self, data):
        """从 seo_track 结果解析音质档位, 按码率降序返回 [{key,label,bitrate,url}]"""
        player = data.get("track_player") if isinstance(data.get("track_player"), dict) else {}
        model = player.get("video_model")
        if isinstance(model, str) and model:
            try:
                model = json.loads(model)
            except Exception:
                model = {}
        out = []
        for idx, item in enumerate((model or {}).get("video_list") or []):
            if not isinstance(item, dict) or item.get("encrypt_info"):
                continue  # 加密流跳过
            meta = item.get("video_meta") or {}
            url = item.get("main_url") or item.get("backup_url")
            if not url:
                continue
            quality = str(meta.get("quality") or idx)
            out.append({"key": quality, "label": self._label(quality, meta.get("bitrate"), idx),
                        "bitrate": int(meta.get("bitrate") or 0), "url": str(url)})
        if not out and player.get("url_player_info"):
            box = ((self._req_url(str(player["url_player_info"])).get("Result") or {}).get("Data") or {})
            for idx, item in enumerate(box.get("PlayInfoList") or []):
                url = item.get("MainPlayUrl") or item.get("BackupPlayUrl")
                if url:
                    quality = str(item.get("Quality") or idx)
                    out.append({"key": quality, "label": self._label(quality, item.get("Bitrate"), idx),
                                "bitrate": int(item.get("Bitrate") or 0), "url": str(url)})
        uniq = {}
        for s in out:
            uniq[(s["key"], s["bitrate"])] = s
        return sorted(uniq.values(), key=lambda x: x["bitrate"], reverse=True)

    @staticmethod
    def _safe(name):
        return str(name or "播放").replace("$", " ").replace("#", " ")

    def _track_detail(self, track_id):
        track_id = str(track_id)
        data = self._seo(track_id)
        track = self._track(data.get("seo_track") or {}) or {"id": track_id}
        card = self._card(track) or {"vod_id": track_id, "vod_name": "汽水音乐", "vod_pic": ""}
        artists = " / ".join(str(a.get("name") or "") for a in (track.get("artists") or [])
                             if isinstance(a, dict) and a.get("name"))
        album = track.get("album") if isinstance(track.get("album"), dict) else {}
        streams = self._streams(data)
        name = self._safe(track.get("name"))
        if streams:
            sources = [s["label"] for s in streams]
            urls = ["%s$a:%s:%s" % (name, track_id, s["key"]) for s in streams]
        else:
            sources, urls = ["汽水音乐"], ["%s$a:%s:auto" % (name, track_id)]
        # VIP/试听歌: 官方档位只能听片段 → 在最前插一条「VIP替代」线路(播放时取完整音源)
        vip = self._is_vip(data)
        if vip:
            sources = ["VIP替代"] + sources
            urls = ["%s$a:%s:vip" % (name, track_id)] + urls
        lyric = str(((data.get("lyric") or {}).get("content")) or "")
        vod = dict(card)
        vod.update({
            "type_name": "音乐",
            "vod_actor": artists,
            "vod_remarks": (str(card.get("vod_remarks") or "").split(" · ")[0] +
                            ("（会员曲·替代源）" if vip else "")),
            "vod_content": "专辑：" + str(album.get("name") or "未知专辑") + ("\n" + lyric[:1500] if lyric else ""),
            "vod_play_from": "$$$".join(sources),
            "vod_play_url": "$$$".join(urls),
        })
        return vod

    def _collection_detail(self, info):
        """合集(歌单/电台/榜单/听歌模式) → 曲目列表"""
        kind, rid = str(info.get("kind") or ""), str(info.get("id") or "")
        if kind == "chart":
            tracks = self._chart_tracks(rid)
        elif kind == "playlist":
            tracks = self._playlist_tracks(rid)
        elif kind == "radio":
            tracks = self._radio_tracks(rid)
        elif kind == "preference":
            tracks = (self._chart_tracks(CHARTS[0][1]) if rid == "default" else
                      self._radio_tracks(NOSTALGIA_RADIO) if rid == "familiar" else
                      self._chart_tracks(CHARTS[1][1]))
        else:
            tracks = []  # 场景模式: 用模式名搜索兜底
        if not tracks:
            tracks = self._search_tracks(info.get("name") or "热门歌曲")
        return self._playlist_card(info, tracks)

    def _search_tracks(self, keyword, page=1):
        payload = {"search_type": "track", "q": str(keyword),
                   "cursor": None if page == 1 else str((page - 1) * 20),
                   "search_id": str(keyword), "search_method": "input", "search_scene": "search_result"}
        data = self._req("/luna/search/track", payload, {"device_platform": "web"})
        group = next((g for g in (data.get("result_groups") or []) if g.get("id") == "tracks"), {})
        return [t for t in (self._track(x) for x in (group.get("data") or [])) if t]

    def _chart_tracks(self, chart_id):
        data = self._req("/luna/charts/" + str(chart_id))
        chart = data.get("chart") if isinstance(data.get("chart"), dict) else {}
        items = (chart.get("track_ranks") or chart.get("tracks") or data.get("track_ranks") or
                 data.get("tracks") or data.get("items") or [])
        return [t for t in (self._track(x) for x in items) if t]

    def _radio_tracks(self, radio_id):
        data = self._req("/luna/feed/radio/tracks", {
            "radio_id": str(radio_id), "played_media": [],
            "feed_radio_media_extra": {"real_groups": []}, "flow_type": 2, "full_media": True})
        return [t for t in (self._track(x) for x in (data.get("items") or [])) if t]

    def _playlist_tracks(self, playlist_id):
        data = self._req("/luna/playlist/detail", {
            "playlist_id": str(playlist_id), "cursor": None, "count": 300, "type": None,
            "feed_playlist_extra": {"har": None, "commerce_block_pattern": None},
            "sort_type": None, "session_id": None, "reverse": False, "ab_param": "",
            "limited_free_scene": 0}, {"max_length": 4194304})
        return [t for t in (self._track(x) for x in (data.get("media_resources") or [])) if t]

    def _playlist_card(self, info, tracks):
        """合集 → 一条多线路 vod(每档音质一条线路, 每首一个分集)"""
        valid = [t for t in tracks if t and t.get("id")]
        streams = []
        for t in valid[:3]:
            try:
                streams = self._streams(self._seo(t["id"]))
            except Exception:
                streams = []
            if streams:
                break
        name = str(info.get("name") or "汽水音乐")
        if streams:
            sources = [s["label"] for s in streams]
            groups = ["#".join("%s$a:%s:%s" % (self._safe(t.get("name")), t["id"], s["key"])
                               for t in valid) for s in streams]
        else:
            sources = ["最高音质"]
            groups = ["#".join("%s$a:%s:auto" % (self._safe(t.get("name")), t["id"]) for t in valid)]
        return {
            "vod_id": self._pack("c", info),
            "vod_name": name,
            "vod_pic": info.get("pic") or "",
            "vod_remarks": info.get("desc") or "",
            "vod_content": info.get("desc") or name,
            "vod_play_from": "$$$".join(sources),
            "vod_play_url": "$$$".join(groups),
        }

    def _video_detail(self, video):
        dur = int(video.get("dur") or 0)
        return {
            "vod_id": self._pack("v", video),
            "vod_name": video.get("name") or "听抖音",
            "vod_pic": video.get("pic") or "",
            "vod_remarks": "%d:%02d" % (dur // 60, dur % 60) if dur else "听抖音",
            "vod_content": video.get("name") or "",
            "vod_play_from": "听抖音",
            "vod_play_url": "播放$v:" + str(video.get("vid")),
        }

    # ------------------------------------------------------------------ 播放
    def playerContent(self, flag, id, vipFlags=None):
        value = str(id or "")
        try:
            if value.startswith("v:"):
                url = ("https://aweme.snssdk.com/aweme/v1/play/?"
                       "video_id=%s&ratio=1080p&line=0" % value[2:])
                return {"parse": 0, "jx": 0, "url": url, "header": {"User-Agent": UA}}
            if value.startswith("a:"):
                _, track_id, quality = value.split(":", 2)
            else:
                track_id, quality = value, "auto"
            data = self._seo(track_id)
            if quality == "vip":
                track = self._track(data.get("seo_track") or {}) or {}
                alt = self._alt_url(track.get("name"))
                if alt:
                    return {"parse": 0, "jx": 0, "url": alt, "music_player": 1,
                            "header": {"User-Agent": UA, "Referer": "https://music.douyin.com/"}}
                quality = "auto"  # 替代源不可用 → 回落官方试听档
            streams = self._streams(data)
            chosen = next((s for s in streams if s["key"] == quality), streams[0] if streams else None)
            if not chosen:
                return {"parse": 1, "jx": 0, "url": value, "header": {}}
            return {"parse": 0, "jx": 0, "url": chosen["url"], "music_player": 1,
                    "header": {"User-Agent": UA, "Referer": "https://music.douyin.com/"}}
        except Exception:
            return {"parse": 1, "jx": 0, "url": value, "header": {}}

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, params):
        return [404, "text/plain", b""]


if __name__ == "__main__":
    print(json.dumps(Spider().homeContent(True), ensure_ascii=False, indent=2))
