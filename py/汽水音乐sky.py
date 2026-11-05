
import base64
import gzip
import hashlib
import http.cookiejar
import json
import os
import random
import re
import socket
import struct
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) SodaMusic/3.5.2 Chrome/136.0.7103.59 "
      "Electron/36.4.0 Safari/537.36")
UA_QR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) SodaMusic/3.2.1 Chrome/136.0.7103.59 "
         "Electron/36.4.0 Safari/537.36")
ICON = ("https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/23/19/5a/"
        "23195ac8-3fbf-d33b-16ed-20854f9afd35/"
        "AppIcon-0-0-1x_U007epad-0-1-0-85-220.png/512x512bb.jpg")

QR_AID = "386088"                       # 汽水 PC 客户端的 passport aid，填错回「非法应用」
QR_GET = "/passport/web/get_qrcode/"
QR_CHECK = "/passport/web/check_qrconnect/"
QR_ME = "/luna/me"                      # 登录态探测: 匿名/失效回 status_code=1000016
SID_KEYS = ("sessionid", "sessionid_ss", "sid_guard", "sid_tt")

CFG = {"port": 8788, "login": True, "page": True, "mode_count": 50}

STATE = {"cookie": "", "nick": "", "loaded": False, "saved": 0.0}
PLAYED = []                             # [{'id','name','action','ts'}] → played_media
CACHE = {}                              # track_id -> (ts, payload)
MODES = {"at": 0.0, "list": []}
QR = {"token": "", "png": "", "expire": 0.0, "status": "new", "msg": "",
      "opener": None, "session": None, "raw": "", "error_code": 0}

LOCK = threading.RLock()                # 登录态 / PLAYED
QR_LOCK = threading.RLock()             # 二维码状态机
CACHE_LOCK = threading.RLock()          # 取流缓存

# ---------------------------------------------------------------- 听歌模式
# 偏好三件套固定在最前（不依赖官方返回，永远可用）
MODES_ORDER = ["默认模式", "熟悉模式", "新鲜模式"]

# 场景 → 官方「歌单」搜索词。
#
# 关键修正：之前每个场景配的是「单曲」搜索词（粤语→搜 "粤语"），拿到的只是
# 标题里带这个词的歌，一堆翻唱合集，跟官方听歌模式差得远。
#
# 实测：官方对匿名请求不认 scene_mode_id（song-tab / discover-mix 一律忽略），
# 但按场景名搜「歌单」，返回的是官方运营人工编好的场景队列——粤语经典金曲里
# 就是《光辉岁月》《海阔天空》《笑看风云》，助眠里就是纯音和雨声。那才是
# 听歌模式的内容来源。取数改为：场景词搜歌单 → 展开曲目 → 轮转打散成池。
MODE_PLAYLIST = {
    "默认模式": ["抖音热歌", "热门 中文 流行"],
    "熟悉模式": ["经典老歌", "怀旧金曲"],
    "新鲜模式": ["华语新歌", "新歌 推荐"],
    "深夜emo": ["emo", "emo 说唱", "伤感 歌单"],
    "助眠模式": ["助眠", "深度睡眠", "ASMR 助眠", "下雨声 助眠"],
    "洗澡": ["洗澡 歌单", "浴室 唱歌", "轻松 流行"],
    "dj模式": ["DJ 舞曲", "夜店 电音", "蹦迪"],
    "动感健身": ["跑步 燃脂", "健身 电音", "运动 节奏"],
    "抖音漫游": ["抖音热歌", "抖音 爆款"],
    "chill放松": ["chill", "慵懒 放松", "lo-fi"],
    "快乐时光": ["快乐 欢快", "元气 歌单", "开心 流行"],
    "电音": ["电音", "EDM", "电子 舞曲"],
    "好运": ["好运 喜庆", "新年 歌单", "喜庆 中文"],
    "图书馆": ["学习 专注", "轻音乐 钢琴", "白噪音 学习"],
    "粤语": ["粤语经典", "粤语老歌", "香港 金曲"],
    "通勤必听": ["通勤", "路上 听", "流行 中文"],
    "失恋必听": ["失恋", "分手 情歌", "伤心 中文"],
    "躺平": ["慵懒", "躺平 歌单", "慢节奏"],
    "欧美": ["欧美流行", "英文歌", "欧美 经典"],
    "打扫": ["打扫 歌单", "轻快 流行", "家务 音乐"],
    "国风": ["国风", "古风", "中国风"],
    "打游戏": ["游戏 战歌", "电竞 燃", "游戏 BGM"],
    "驾车": ["车载 音乐", "驾驶 歌单", "开车 音乐"],
    "专注模式": ["专注 学习", "纯音乐 专注", "白噪音"],
    "说唱": ["中文说唱", "rap", "嘻哈"],
    "沉浸0.8x": ["慢歌 抒情", "沉浸 女声", "夜景 慢歌"],
    "夜晚": ["夜晚 歌单", "晚安", "夜色 抒情"],
    "治愈": ["治愈系", "温柔 疗愈", "治愈 女声"],
    "轻音乐": ["轻音乐", "纯音乐", "钢琴 轻音乐"],
    "小酒馆": ["小酒馆", "民谣 酒馆", "爵士 微醺"],
    "ktv必点": ["KTV 必点", "合唱 金曲", "经典 对唱"],
    "起床": ["晨间 歌单", "起床 轻快", "元气 早晨"],
    "浪漫情歌": ["浪漫 情歌", "甜蜜 对唱", "恋爱 歌单"],
    "摇滚": ["摇滚", "中国摇滚", "摇滚 经典"],
    "r&b": ["R&B", "中文 R&B", "soul"],
    "佛系时间": ["佛系", "安静 纯音乐", "禅意"],
    "怀旧老歌": ["怀旧 老歌", "经典 老歌", "80年代"],
    "民谣": ["民谣", "中文民谣", "独立民谣"],
    "甜美女声": ["甜美女声", "女声 甜", "治愈 女声"],
    "k-pop": ["K-pop", "韩语 歌单", "韩国 流行"],
    "日语": ["日语 歌单", "J-POP", "日系"],
    "旅行": ["旅行 歌单", "公路 旅行", "出发"],
    "摸鱼": ["摸鱼 歌单", "上班 听", "轻松 背景"],
    "儿歌": ["儿歌", "儿童 歌曲", "宝宝 歌单"],
    "雨天": ["雨天 歌单", "下雨 听", "雨天 抒情"],
    "海边": ["海边 歌单", "夏日 海边", "海风"],
    "乡村": ["乡村音乐", "country", "民谣 乡村"],
    "古典": ["古典音乐", "钢琴 古典", "交响"],
}

# 偏好模式（非场景）继续走官方个性化队列
PREF_MODES = {"默认模式", "熟悉模式", "新鲜模式"}

JUNK = ("串烧", "连播", "合集", "合辑", "精选集", "伴奏", "铃声", "DJ版")

# 兜底电台：任何来源都取不到歌时用（实测长期可用）
FALLBACK_RADIO = "7408841207276748809"

# ---------------------------------------------------------------- 完整音源(酷我)
KUWO_SEARCH = "https://search.kuwo.cn/r.s"
KUWO_SIGN = "https://nmobi.kuwo.cn/mobi.s"
KUWO_SOURCE = "kwplayer_ar_4.4.2.7_B_nuoweida_vh.apk"
ALT_CACHE = {}
ALT_LOCK = threading.Lock()

ALT_NOISE_CJK = ("伴奏", "纯音乐", "铃声", "翻唱", "改编", "串烧", "合唱", "对唱", "童声",
                 "钢琴", "吉他", "唢呐", "二胡", "环绕", "现场", "慢摇", "片段",
                 "试听", "演唱会", "巡演", "音乐节", "原曲", "旧版")
ALT_NOISE_EN = ("dj", "remix", "live", "cover", "inst", "epic", "demo", "remaster", "ktv", "3d")


# ============================================================================
# 存储：登录态 + 已播列表（同一份文件，跨会话保持）
# ============================================================================

def _data_path():
    """状态文件：优先 py 源同目录(与旧版同名，老用户登录态直接复用)，不可写退临时目录。"""
    cands = []
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here:
            cands.append(os.path.join(here, "qishui_login.json"))
    except Exception:
        pass
    try:
        cands.append(os.path.join(tempfile.gettempdir(), "qishui_login.json"))
    except Exception:
        pass
    for path in cands:
        try:
            folder = os.path.dirname(path)
            if folder and os.path.isdir(folder) and os.access(folder, os.W_OK):
                return path
        except Exception:
            continue
    return cands[0] if cands else "qishui_login.json"


def _state_load():
    with LOCK:
        if STATE["loaded"]:
            return STATE
        STATE["loaded"] = True
        try:
            with open(_data_path(), "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict):
                STATE["cookie"] = str(data.get("cookie") or "")
                STATE["nick"] = str(data.get("nick") or "")
                STATE["saved"] = float(data.get("saved") or 0)
                rows = data.get("played") or []
                if isinstance(rows, list):
                    PLAYED[:] = [r for r in rows if isinstance(r, dict) and r.get("id")][-80:]
        except Exception:
            pass
        return STATE


def _state_save():
    with LOCK:
        STATE["saved"] = time.time()
        try:
            with open(_data_path(), "w", encoding="utf-8") as fp:
                json.dump({"cookie": STATE["cookie"], "nick": STATE["nick"],
                           "saved": STATE["saved"], "played": PLAYED[-80:]},
                          fp, ensure_ascii=False)
        except Exception:
            pass


def cookie_now():
    with LOCK:
        _state_load()
        return STATE["cookie"]


def nick_now():
    with LOCK:
        _state_load()
        return STATE["nick"]


def logged_in():
    return bool(cookie_now())


def qr_log(msg):
    """扫码链路诊断日志（源同目录 qishui_qr.log）：官方确认后到底给了什么，
    只有看到 raw 响应才能判断，纯 HTTP 与签名页两条路的差别全在这里。"""
    try:
        path = os.path.join(os.path.dirname(_data_path()), "qishui_qr.log")
        if os.path.exists(path) and os.path.getsize(path) > 200000:
            os.remove(path)
        with open(path, "a", encoding="utf-8") as fp:
            fp.write("%s %s\n" % (time.strftime("%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def _qr_follow(payload, sess):
    """confirmed 后跟一跳 redirect 收会话 Cookie。

    官方文档实测：确认后的登录态不在响应体、常规也不带 Set-Cookie，它挂在
    「扫码页那个浏览器会话」里。跟着 redirect_url 走一跳，运气好能通过
    票据把 sessionid 种到我们这边；拿不到就说明必须走签名页/手工 Cookie。
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    cands = []
    for src in (data, payload):
        if not isinstance(src, dict):
            continue
        for k in ("redirect_url", "redirect_uri", "url", "desc_url"):
            v = src.get(k)
            if isinstance(v, str) and v.startswith("http"):
                cands.append(v)
        extra = src.get("extra")
        if isinstance(extra, str) and "http" in extra:
            try:
                j = json.loads(extra)
            except Exception:
                j = {}
            if isinstance(j, dict):
                for k in ("redirect_url", "redirect_uri", "url"):
                    v = j.get(k)
                    if isinstance(v, str) and v.startswith("http"):
                        cands.append(v)
    seen = set()
    for url in cands[:3]:
        if url in seen:
            continue
        seen.add(url)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA_QR, "Referer": API + "/",
                "Accept": "text/html,application/xhtml+xml"})
            with sess["opener"].open(req, timeout=10) as r:
                r.read(2048)
            qr_log("follow ok %s" % url[:120])
        except Exception as e:
            qr_log("follow fail %s (%s)" % (url[:100], e))


def qr_url(base):
    """封面图地址带 token 指纹：App 会缓存封面图，不带指纹时用户扫到的
    可能是上一张已作废的码，手机点确认后这边永远等不到。"""
    with QR_LOCK:
        tk = (QR.get("token") or "")[:8]
    return "%s/qr.png?t=%d&k=%s" % (base, int(time.time()), tk)


def save_cookie(cookie, nick=""):
    with LOCK:
        STATE["cookie"] = str(cookie or "")
        if nick:
            STATE["nick"] = str(nick)
        _state_save()


def forget_login():
    with LOCK:
        STATE["cookie"] = ""
        STATE["nick"] = ""
        _state_save()


# ============================================================================
# HTTP：所有 uplink 都从这里走
# ============================================================================

def _open(url, data=None, headers=None, method=None, timeout=15):
    head = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
            "Referer": "https://music.douyin.com/", "Accept-Encoding": "gzip"}
    head.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=head, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if str(r.headers.get("Content-Encoding", "")).lower() == "gzip":
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        return raw


def _json(url, data=None, headers=None, method=None, timeout=15):
    return json.loads(_open(url, data, headers, method, timeout).decode("utf-8", "replace"))


def api(path, body=None, query=None, auth=True, timeout=15):
    """内容接口。auth=True 自动带登录 Cookie；取流(seo_track)一律 auth=False。"""
    url = API + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if auth:
        cookie = cookie_now()
        if cookie:
            headers["Cookie"] = cookie
    try:
        out = _json(url, data, headers, "POST" if data else "GET", timeout)
        return out if isinstance(out, dict) else {}
    except Exception as e:
        return {"_error": str(e)}


def qs_call(path, method="GET", params=None, body=None, opener=None, headers=None,
            timeout=20):
    """passport 专用：URL 参数 + form 表单，返回原始 dict。"""
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    head = dict(headers or {})
    data = None
    if body:
        data = urllib.parse.urlencode(body).encode("utf-8")
        head["Content-Type"] = "application/x-www-form-urlencoded"
        head["x-ss-stub"] = hashlib.md5(data).hexdigest().upper()
    req = urllib.request.Request(url, data=data, headers=head, method=method)
    op = opener or urllib.request.build_opener()
    with op.open(req, timeout=timeout) as r:
        raw = r.read()
        if str(r.headers.get("Content-Encoding", "")).lower() == "gzip":
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
    return json.loads(raw.decode("utf-8", "replace"))


# ============================================================================
# 整形：官方结构 → 统一形状
# ============================================================================

def _first(value):
    return value[0] if isinstance(value, list) and value else value


def _img(image):
    """封面：urls 里形如 https://p3-luna.douyinpic.com/img/ 需拼 uri + 模板后缀"""
    if not isinstance(image, dict):
        return ""
    uri = str(image.get("uri") or "")
    url = str(_first(image.get("urls")) or "")
    if url and url.rstrip("/").endswith("/img") and uri:
        full = url.rstrip("/") + "/" + uri.lstrip("/")
        tpl = str(image.get("template_prefix") or "")
        return full + ("~" + tpl + "-ori.image" if tpl else "")
    return url or uri


def _track(obj):
    """从各种嵌套里抠出 track 对象（feed/搜索/歌单/电台的层级各不相同）。"""
    if not isinstance(obj, dict):
        return None
    if obj.get("id") and (obj.get("name") or obj.get("title")):
        return obj
    for path in (("track",), ("track_wrapper", "track"),
                 ("entity", "track_wrapper", "track"), ("entity", "track")):
        cur = obj
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        if isinstance(cur, dict) and cur.get("id"):
            return cur
    return None


def _artists(track):
    return " / ".join(str(a.get("name") or "") for a in (track.get("artists") or [])
                      if isinstance(a, dict) and a.get("name"))


def _dur(t):
    """官方 duration 是毫秒；歌曲不可能超过 2000 秒，超过就折回秒。"""
    for k in ("duration", "video_duration", "audio_duration"):
        v = t.get(k)
        if isinstance(v, (int, float)) and v:
            v = int(v)
            return int(v / 1000) if v > 2000 else v
    return 0


def norm(t):
    album = t.get("album") if isinstance(t.get("album"), dict) else {}
    label = t.get("label_info") if isinstance(t.get("label_info"), dict) else {}
    return {
        "id": str(t.get("id") or ""),
        "name": str(t.get("name") or "未知歌曲"),
        "artist": _artists(t) or "未知歌手",
        "album": str(album.get("name") or ""),
        "cover": _img(album.get("url_cover") or t.get("url_cover") or {}),
        "duration": _dur(t),
        "vip": bool(label.get("only_vip_playable") or label.get("only_vip_download")),
    }


def _push(bucket, items):
    seen = {t["id"] for t in bucket}
    for it in items:
        t = _track(it)
        if not t:
            continue
        n = norm(t)
        if n["id"] and n["id"] not in seen:
            seen.add(n["id"])
            bucket.append(n)
    return bucket


def play_event(track_id, action="skip", name=""):
    """把一次播放行为写进 PLAYED —— 下一次 build_feed 会作为 played_media 送回上游。

    这是整套「联动它算法」里唯一真正起作用的东西：不是我们本地打分，
    而是把行为原样交回官方推荐器，让它自己更新会话内的兴趣状态。
    """
    tid = str(track_id or "")
    if not tid:
        return
    with LOCK:
        PLAYED[:] = [r for r in PLAYED if r["id"] != tid]
        PLAYED.append({"id": tid, "name": str(name or ""), "action": str(action or "skip"),
                       "ts": time.time()})
        del PLAYED[:-80]
        _state_save()


def _played_media(limit=20):
    with LOCK:
        rows = PLAYED[-limit:]
    return [{"id": r["id"], "type": "track"} for r in rows if r.get("id")]


# ============================================================================
# 听歌模式墙
# ============================================================================

def mode_key(name):
    return re.sub(r"\s+", "", str(name or "")).lower()


def load_modes():
    """官方模式墙（实测 45 个）+ 偏好三件套。5 分钟缓存。"""
    if time.time() - MODES["at"] < 300 and MODES["list"]:
        return MODES["list"]
    rows = []
    for name in MODES_ORDER:
        rows.append({"key": mode_key(name), "name": name, "sid": 0, "queue": "",
                     "kind": "preference"})
    data = api("/luna/feed/mode", {"ab_param": "", "feed_extra": None})
    for group in data.get("feed_mode_block") or []:
        for m in group.get("feed_mode") or []:
            scene = ((m.get("entity") or {}).get("feed_scene_mode") or {})
            name = str(m.get("text") or "").strip()
            if not name:
                continue
            rows.append({"key": mode_key(name), "name": name,
                         "sid": int(scene.get("scene_mode_id") or 0),
                         "queue": str(scene.get("sub_queue_type") or ""),
                         "kind": "scene"})
    out, seen = [], set()
    for r in rows:
        if r["key"] in seen:
            continue
        seen.add(r["key"])
        r["kws"] = MODE_PLAYLIST.get(r["key"], [])
        r["kw"] = r["kws"][0] if r["kws"] else ""
        out.append(r)
    if len(out) > len(MODES_ORDER):
        MODES["list"], MODES["at"] = out, time.time()
    elif not MODES["list"]:
        MODES["list"] = out          # 官方墙挂了也别让界面空着
    return MODES["list"]


def get_mode(key):
    modes = load_modes()
    for m in modes:
        if m["key"] == mode_key(key):
            return m
    for m in modes:
        if mode_key(m["name"]) == mode_key(key):
            return m
    return modes[0]


# ============================================================================
# 推荐流：五种来源
# ============================================================================

def src_song_tab(want, rounds=3):
    """官方个性化推荐队列。匿名是公共池，登录后按账号画像出。

    played_media 就是这里带上去的：带着它请求，返回的就不是同一批歌。
    """
    out = []
    played = _played_media()
    for i in range(max(1, rounds)):
        if len(out) >= want:
            break
        body = {"played_media": played, "is_first_request": i == 0,
                "is_did_first_request": i > 0,
                "feed_counts": {"mix_session_count": i}}
        data = api("/luna/pc/feed/song-tab", body)
        items = data.get("items") or []
        if not items:
            break
        _push(out, items)
    return out


def src_discover_mix(mode, want):
    """登录后才真正生效：官方按 scene_mode_id + sub_queue_type 发内容。"""
    out = []
    if not mode.get("sid"):
        return out
    body = {"block_type": "scene_mode", "sub_channel_id": 0, "exposure_radio_list": [],
            "count": 20, "cursor": "", "session_id": "",
            "scene_mode_id": int(mode["sid"])}
    if mode.get("queue"):
        body["sub_queue_type"] = mode["queue"]
    data = api("/luna/pc/discover/mix", body)
    playlists, radios = [], []
    for block in data.get("inner_block") or []:
        for res in block.get("resources") or []:
            ent = res.get("entity") if isinstance(res.get("entity"), dict) else {}
            inline = _track(ent)
            if inline:
                _push(out, [inline])
            pl = ent.get("playlist")
            if isinstance(pl, dict) and pl.get("id"):
                playlists.append(str(pl["id"]))
            rd = ent.get("radio")
            if isinstance(rd, dict) and rd.get("id"):
                radios.append(str(rd["id"]))
    for pid in playlists[:1]:                 # 只展开一个，别把首屏拖慢
        if len(out) >= want:
            break
        _push(out, src_playlist(pid, 30))
    for rid in radios[:1]:
        if len(out) >= want:
            break
        _push(out, src_radio(rid, 6))
    return out


def src_playlist(pid, count=30):
    data = api("/luna/playlist/detail", {
        "playlist_id": str(pid), "cursor": None, "count": count, "type": None,
        "feed_playlist_extra": {"har": None, "commerce_block_pattern": None},
        "sort_type": None, "session_id": None, "reverse": False, "ab_param": "",
        "limited_free_scene": 0})
    return [n for n in (norm(t) for t in (_track(x) for x in data.get("media_resources") or [])
                        if t) if n["id"]]


def src_radio(rid, want=6):
    out = []
    for _ in range(max(1, (want // 6) + 1)):
        data = api("/luna/feed/radio/tracks", {
            "radio_id": str(rid), "played_media": _played_media(),
            "feed_radio_media_extra": {"real_groups": []},
            "flow_type": 2, "full_media": True})
        items = data.get("items") or []
        if not items:
            break
        _push(out, items)
        if len(out) >= want:
            break
    return out


def src_search(kw, pages=2):
    out = []
    for p in range(max(1, pages)):
        body = {"search_type": "track", "q": kw,
                "cursor": None if p == 0 else str(p * 20),
                "search_id": hashlib.md5(str(kw).encode("utf-8")).hexdigest(),
                "search_method": "input", "search_scene": "search_result"}
        data = api("/luna/search/track", body, {"device_platform": "web"})
        group = next((g for g in data.get("result_groups") or [] if g.get("id") == "tracks"), {})
        if not group.get("data"):
            break
        _push(out, group["data"])
    return out


# ---------------------------------------------------------------- 场景曲目池
# 官方场景队列（scene_mode_id）只在「登录 + 真实设备签名」下才认，匿名请求
# song-tab / discover-mix 都会忽略它，只回通用热门池——这就是之前场景模式
# 只能退回「按名字搜单曲」的原因。
#
# 换一条官方内容链：场景词 → 搜官方歌单 → 展开曲目 → 轮转打散。歌单是官方
# 运营人工编好的场景队列，粤语给的真是《光辉岁月》《海阔天空》，助眠给的
# 真是纯音和雨声，风格与听歌模式一致。

POOL = {}          # mode_key -> (ts, [track])
POOL_CURSOR = {}   # mode_key -> 已消耗到池子第几首
POOL_LOCK = threading.Lock()
POOL_TTL = 1800


def _pmap(fn, items, workers=4):
    """并发 map；单个失败返回 None，并发不可用时自动串行（内核差异兜底）。"""
    def safe(x):
        try:
            return fn(x)
        except Exception:
            return None
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(safe, items))
    except Exception:
        return [safe(x) for x in items]


def _pl_search(kw, limit=2):
    """按关键词搜官方歌单，返回 [(playlist_id, name)]。"""
    body = {"search_type": "playlist", "q": kw, "cursor": None,
            "search_id": hashlib.md5(str(kw).encode("utf-8")).hexdigest(),
            "search_method": "input", "search_scene": "search_result"}
    data = api("/luna/search/playlist", body, {"device_platform": "web"})
    out = []
    for grp in data.get("result_groups") or []:
        for it in grp.get("data") or []:
            ent = it.get("entity") or it
            pl = ent.get("playlist") if isinstance(ent.get("playlist"), dict) else ent
            if not isinstance(pl, dict):
                continue
            pid = str(pl.get("id") or "")
            name = str(pl.get("name") or pl.get("title") or "")
            if pid and name:
                out.append((pid, name))
    junk = ("串烧", "连播", "合辑", "拼盘", "电台合集")
    out = [x for x in out if not any(j in x[1] for j in junk)]
    return out[:limit]


def _rr_merge(groups):
    """歌单轮转合并：相邻两首来自不同歌单，避免连着听十首都像一个歌单的尾巴。"""
    out, seen = [], set()
    rounds = max([len(g) for g in groups] or [0])
    for i in range(rounds):
        for g in groups:
            if i >= len(g):
                continue
            t = g[i]
            if t["id"] and t["id"] not in seen:
                seen.add(t["id"])
                out.append(t)
    return out


# 这些场景本来就靠 DJ/Remix 撑场，质量过滤时放行
KEEP_DJ = {"dj模式", "电音", "动感健身", "抖音漫游"}
BAD_MARK = ("remix", "dj", "bpm", "3d", "环绕", "高音质", "无损", "live版", "live 版",
            "现场版", "(live", "（live", "伴奏", "铃声", "翻唱版", "串烧", "连播", "拼盘")


def _pl_clean(tracks, key):
    """池子质量关：非电音场景把 Remix/DJ版/live 版/伴奏全部拦掉。"""
    if key in KEEP_DJ:
        return [t for t in tracks if "伴奏" not in t["name"] and "铃声" not in t["name"]]
    out = []
    for t in tracks:
        low = t["name"].lower()
        if any(b in low for b in BAD_MARK):
            continue
        out.append(t)
    return out


def scene_pool(mode, refresh=False):
    """构建并缓存一个场景的曲目池（约 60~200 首）。"""
    key = mode["key"]
    now = time.time()
    with POOL_LOCK:
        hit = POOL.get(key)
    if hit and not refresh and now - hit[0] < POOL_TTL and len(hit[1]) >= 30:
        return hit[1]

    kws = mode.get("kws") or ([mode["kw"]] if mode.get("kw") else [])
    if not kws:
        return []
    picks = []
    for r in _pmap(lambda k: _pl_search(k, 3), kws[:4], 4):
        if r:
            picks.extend(r)
    seen, pids = set(), []
    for pid, _name in picks:
        if pid not in seen:
            seen.add(pid)
            pids.append(pid)
    groups = [g for g in _pmap(lambda p: src_playlist(p, 50), pids[:9], 5) if g]
    tracks = _pl_clean(_rr_merge(groups), key)
    with POOL_LOCK:
        POOL[key] = (now, tracks)
        POOL_CURSOR.setdefault(key, 0)
    return tracks


def pool_take(mode, n=6):
    """从池子里按游标取 n 首，跳过最近播过的；池子见底就换一批。"""
    key = mode["key"]
    pool = scene_pool(mode)
    if not pool:
        return []
    with POOL_LOCK:
        cur = POOL_CURSOR.get(key, 0)
    if cur >= len(pool) - 2:
        pool = scene_pool(mode, refresh=True)
        cur = 0
        with POOL_LOCK:
            POOL_CURSOR[key] = 0
    with LOCK:
        recent = {r["id"] for r in PLAYED[-40:]}
    out, consumed, names = [], 0, set()
    for t in pool[cur:]:
        consumed += 1
        # 官方库里同曲多版本极多（罗文/徐小凤各一版《顺流逆流》），按歌名去重
        if t["id"] in recent or t["name"] in names:
            continue
        names.add(t["name"])
        out.append(t)
        if len(out) >= n:
            break
    with POOL_LOCK:
        POOL_CURSOR[key] = cur + max(1, consumed)
    return out


def build_feed(key, n=6):
    """取数：所有模式先走官方运营歌单池（人工编好的场景队列），官方个性化
    队列（played_media 闭环）补齐剩余名额——匿名时 song-tab 只有 20 来首
    热门歌随机洗牌，撑不起任何模式。"""
    mode = get_mode(key)
    tracks, tried = [], []
    part = pool_take(mode, n)
    tried.append("pool:%d" % len(part))
    tracks += part
    if len(tracks) < n:
        part = src_song_tab(n - len(tracks))
        tried.append("song_tab:%d" % len(part))
        ids = {x["id"] for x in tracks}
        tracks += [t for t in part if t["id"] not in ids]
    if len(tracks) < n:
        part = src_radio(FALLBACK_RADIO, n - len(tracks) + 4)
        tried.append("radio:%d" % len(part))
        ids = {x["id"] for x in tracks}
        tracks += [t for t in part if t["id"] not in ids]
    # 合集/串烧往后放，别占首屏
    tracks.sort(key=lambda t: 1 if any(j in t["name"] for j in JUNK) else 0)
    # 最近播过的不再出现（全被过滤掉时保留原样，避免空列表）
    with LOCK:
        recent = [r["id"] for r in PLAYED[-30:]]
    tracks = [t for t in tracks if t["id"] not in recent] or tracks
    return {"list": tracks[:n], "mode": mode, "src": ",".join(tried) or "-"}


def search_tracks(word, want=30):
    """搜索入口的净化：过滤合集/伴奏，控制条数。"""
    out = []
    for t in src_search(str(word or "").strip(), 2):
        if any(j in t["name"] for j in JUNK):
            continue
        out.append(t)
        if len(out) >= want:
            break
    return out


# ============================================================================
# 完整音源：酷我直连
# ============================================================================

def _norm_text(s):
    s = re.sub(r"[\(（\[【].*?[\)）\]】]", "", str(s or ""))
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", s.lower())


def _alt_score(item, name, artist):
    """名字对不上直接 -1；多余字符越多越不像原版；伴奏/翻唱/live 重罚。

    ★ 教训：不这么打分时，搜「孤勇者」会选中「孤勇者(热血epic版)」(48 秒短版)，
      而真原版落选。所以「去掉标题后还剩多少字符」是这里唯一有效的判据。
    """
    raw = str(item.get("SONGNAME") or "")
    flat, target = _norm_text(raw), _norm_text(name)
    if not flat or not target or target not in flat:
        return -1
    extra = len(flat.replace(target, "", 1))
    score = 100 - min(extra, 30) * 3
    low = raw.lower()
    if any(b in low for b in ALT_NOISE_CJK) or any(
            re.search(r"(?<![a-z0-9])" + re.escape(b) + r"(?![a-z0-9])", low)
            for b in ALT_NOISE_EN):
        score -= 45
    if artist:
        mine = [x for x in (_norm_text(y) for y in re.split(r"[/&、,，]", artist)) if x]
        theirs = _norm_text(item.get("ARTIST"))
        if mine and theirs:
            score += 40 if any(x in theirs or theirs in x for x in mine) else -25
    return score


def _kw_search(keyword, rn=10):
    url = ("%s?client=kt&pn=0&rn=%d&all=%s&vipver=1&ft=music&encoding=utf8&rformat=json&mobi=1"
           % (KUWO_SEARCH, rn, urllib.parse.quote(str(keyword))))
    try:
        txt = _open(url, headers={"User-Agent": "okhttp/3.10.0"},
                    timeout=8).decode("utf-8", "replace")
        try:
            data = json.loads(txt)
        except Exception:
            data = json.loads(txt.replace("'", '"'))
        return data.get("abslist") or []
    except Exception:
        return []


def _kw_rid(name, artist):
    first = re.split(r"[/&、,，]", artist or "")[0].strip()
    queries = ([name + " " + first] if first else []) + [name]
    best, best_score, seen = "", -1, set()
    for kw in queries:
        for pos, item in enumerate(_kw_search(kw)):
            rid = str(item.get("DC_TARGETID") or item.get("MUSICRID") or "").replace("MUSIC_", "").strip()
            if not rid or rid in seen:
                continue
            seen.add(rid)
            sc = _alt_score(item, name, artist)
            if sc < 0:
                continue
            sc -= pos * 2
            if sc > best_score:
                best, best_score = rid, sc
        if best and best_score >= 55:
            break
    return best


def alt_url(name, artist=""):
    """酷我 320k 完整版直链 → (url, ext)；失败 ("","")。"""
    name = str(name or "").strip()
    if not name:
        return "", ""
    key = name.lower() + "|" + str(artist or "").lower()
    with ALT_LOCK:
        hit = ALT_CACHE.get(key)
    if hit and time.time() - hit[0] < 900:
        return hit[1], hit[2]
    rid = _kw_rid(name, artist)
    if not rid:
        return "", ""
    url = ("%s?f=web&user=0&source=%s&type=convert_url_with_sign&rid=%s&br=320kmp3&format=mp3"
           % (KUWO_SIGN, KUWO_SOURCE, rid))
    try:
        data = json.loads(_open(url, headers={"User-Agent": "okhttp/3.10.0"},
                                timeout=8).decode("utf-8", "replace"))
        link = str((data.get("data") or {}).get("url") or "")
    except Exception:
        link = ""
    if link.startswith("http"):
        with ALT_LOCK:
            ALT_CACHE[key] = (time.time(), link, "mp3")
        return link, "mp3"
    return "", ""


# ============================================================================
# 取流 + 歌词
# ============================================================================

def _streams(data):
    """seo_track → 可用档位，按码率降序。跳过 encrypted（加密流播不了）。"""
    player = data.get("track_player") or {}
    model = player.get("video_model")
    if isinstance(model, str):
        try:
            model = json.loads(model)
        except Exception:
            model = {}
    rows = []
    for item in (model or {}).get("video_list") or []:
        if not isinstance(item, dict) or item.get("encrypt_info"):
            continue
        meta = item.get("video_meta") or {}
        url = item.get("main_url") or item.get("backup_url")
        if not url:
            continue
        rows.append({"url": str(url),
                     "bitrate": int(meta.get("bitrate") or meta.get("real_bitrate") or 0),
                     "quality": str(meta.get("quality") or ""),
                     "size": int(meta.get("size") or 0)})
    rows.sort(key=lambda s: s["bitrate"], reverse=True)
    return rows


QUALITY_LABEL = {"highest": "最高", "higher": "较高", "medium": "标准"}


def resolve(track_id, prefer_alt=False):
    """一首歌 → {url, ext, source, full, lyric, track}。

    · 官方流永远走匿名会话（登录态可能发加密/VIP 档，反而播不了）
    · 官方流是片段（字节数÷码率 < 时长×80%）→ 换酷我完整版
    · prefer_alt=True 时先试完整版（详情页「320k」那条线路）
    """
    key = str(track_id or "")
    if not key:
        return {"url": "", "error": "missing id"}
    if not prefer_alt:
        with CACHE_LOCK:
            hit = CACHE.get(key)
        if hit and time.time() - hit[0] < 240:
            return hit[1]

    data = api("/luna/h5/seo_track", query={"track_id": key, "device_platform": "web"},
               auth=False)
    streams = _streams(data)
    best = streams[0] if streams else None
    track = _track(data.get("seo_track") or {}) or {}
    tk = norm(track) if track else None

    covered = 0.0
    if best and best["bitrate"] and best["size"]:
        covered = best["size"] * 8.0 / best["bitrate"]
    full = bool(tk and tk["duration"] and covered >= tk["duration"] * 0.8)

    out = {"url": best["url"] if best else "", "ext": "m4a",
           "bitrate": best["bitrate"] if best else 0,
           "quality": QUALITY_LABEL.get((best or {}).get("quality", ""),
                                        (best or {}).get("quality", "")),
           "covered": round(covered, 1), "full": full, "source": "官方音源",
           "lyric": parse_lyric((data.get("lyric") or {}).get("content") or ""),
           "track": tk}

    if tk and (prefer_alt or not full):
        alt, ext = alt_url(tk["name"], tk["artist"])
        if alt:
            out.update({"url": alt, "ext": ext, "bitrate": 320000,
                        "quality": "320k", "source": "完整版", "full": True})

    if not prefer_alt:
        with CACHE_LOCK:
            CACHE[key] = (time.time(), out)
            if len(CACHE) > 400:
                for k in sorted(CACHE, key=lambda x: CACHE[x][0])[:120]:
                    CACHE.pop(k, None)
    return out


def parse_lyric(raw):
    """官方给逐字时间轴：[行开始ms,行时长]<字符偏移,字符时长,? >字…

    这里只保留行级（页面按行高亮），比逐字更稳：逐字数据经常有缺字。
    """
    lines = []
    for line in str(raw or "").splitlines():
        m = re.match(r"^\[(\d+),(\d+)\](.*)$", line.strip())
        if not m:
            continue
        start, text = int(m.group(1)), re.sub(r"<[^>]*>", "", m.group(3))
        text = re.sub(r"\s+", "", text) if re.search(r"[\u4e00-\u9fff]", text) else text.strip()
        if text:
            lines.append({"t": round(start / 1000.0, 2), "text": text})
    lines.sort(key=lambda x: x["t"])
    return lines


# ============================================================================
# 扫码登录（官方 passport，实测可用）
# ============================================================================

def _digits(n):
    s = str(random.randint(1, 8))
    while len(s) < n:
        s += str(random.randint(0, 9))
    return s


def _qr_session():
    with QR_LOCK:
        if QR.get("opener") and QR.get("session"):
            return QR["session"]
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        sess = {"device_id": _digits(16), "install_id": _digits(15),
                "ms_token": os.urandom(66).hex()[:88] + "==",
                "portrait": "%s-%s-%s-%s-%s.login" % (
                    _digits(8), _digits(4), _digits(4), _digits(4), _digits(11)),
                "jar": jar}
        QR["opener"], QR["session"] = opener, sess
        return sess


def _qr_params(sess, biz):
    return {"passport_jssdk_version": "2.4.13", "passport_jssdk_type": "normal",
            "is_from_ttaccountsdk": "1", "aid": QR_AID, "language": "zh",
            "account_sdk_source": "web", "p_js_v": "2.4.13", "p_js_t": "pro",
            "p_zt": "3.3.5", "p_ver": "1.0.29", "request_host": "app%3A%2F%2Fresources",
            "p_bd": "1.0.0.41", "biz_trace_id": biz, "is_new_login": "1",
            "is_from_iesaccountsaas": "1", "device_id": sess["device_id"],
            "install_id": sess["install_id"], "did": sess["device_id"],
            "iid": sess["install_id"], "device_platform": "PC", "version_code": "3.5.2",
            "account_sdk_source_info": "00", "msToken": sess["ms_token"]}


def _qr_call(sess, method, path, extra=None, body=None):
    biz = "%08x" % random.getrandbits(32)
    params = _qr_params(sess, biz)
    params.update(extra or {})
    headers = {"Accept": "application/json, text/javascript", "User-Agent": UA_QR,
               "Referer": API + "/", "x-tt-passport-verify-portrait": sess["portrait"],
               "x-tt-passport-trace-id": biz}
    return qs_call(path, method, params, body, opener=QR["opener"], headers=headers)


def qr_new(force=False):
    if not CFG["login"]:
        return {"error": "登录已在配置里关闭"}
    with QR_LOCK:
        if not force and QR["png"] and time.time() < QR["expire"] - 5:
            return {"png": QR["png"], "expire": QR["expire"]}
    sess = _qr_session()
    try:
        payload = _qr_call(sess, "GET", QR_GET, {
            "next": API, "need_logo": "false", "need_short_url": "false", "is_new_login": "1"})
    except Exception as e:
        return {"error": "创建二维码失败：%s" % e}
    data = payload.get("data") or {}
    if not data.get("token"):
        return {"error": payload.get("message") or "创建二维码失败"}
    with QR_LOCK:
        expire = time.time() + 170
        exp = data.get("expire_time")
        if isinstance(exp, (int, float)):
            expire = float(exp) if exp > 10 ** 9 else time.time() + float(exp)
        old = [t for t in (QR.get("tokens") or []) if t != data["token"]][-3:]
        QR.update({"token": data["token"], "png": data.get("qrcode") or "",
                   "expire": expire, "status": "new", "msg": "", "raw": "",
                   "error_code": 0, "tokens": old + [data["token"]]})
    qr_log("qr_new token=%s expire=%ds" % (data["token"][:12], int(expire - time.time())))
    return {"png": QR["png"], "expire": QR["expire"]}


def qr_poll():
    if logged_in():
        return {"status": "confirmed", "msg": "已登录", "ok": True, "nick": nick_now()}
    with QR_LOCK:
        token, prev = QR["token"], QR["status"]
        hist = list(QR.get("tokens") or [])
    if not token:
        return {"status": prev or "new", "msg": "二维码已失效，请刷新", "ok": False}
    sess = _qr_session()
    # App 会缓存封面图，用户扫到的可能是前一两张码；把最近几个 token 一起查，
    # 命中哪个都算数，免得「手机已确认、这边还在等」。
    order = [token] + [t for t in reversed(hist) if t != token][:2]
    best, best_rank = None, -1
    rank_of = {"confirmed": 3, "3": 3, "success": 3, "scanned": 2, "2": 2,
               "scanning": 2, "new": 1, "1": 1}
    try:
        for tk in order:
            p = _qr_call(sess, "POST", QR_CHECK, {}, {
                "need_logo": "false", "need_short_url": "false", "is_frontier": "true",
                "token": tk, "is_new_login": "1", "next": API})
            d = p.get("data") if isinstance(p.get("data"), dict) else p
            r = rank_of.get(str(d.get("status") or ""), 0)
            if r > best_rank:
                best, best_rank = p, r
            if r >= 3:
                break
    except Exception as e:
        return {"status": prev, "msg": "网络异常：%s" % e, "ok": False}
    payload = best if best is not None else {"data": {"status": "new"}}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload

    raw = str(data.get("status") or "")
    code = int(data.get("error_code") or 0)
    status = {"new": "new", "1": "new", "scanned": "scanned", "scanning": "scanned",
              "2": "scanned", "confirmed": "confirmed", "3": "confirmed",
              "success": "confirmed", "expired": "expired"}.get(raw, raw)
    if code == 2:
        status = "expired"
    if code in (7, 2046):                     # 限流 / 二次验证：状态不倒退
        status = prev or status
    with QR_LOCK:
        QR["raw"], QR["error_code"] = raw, code
        if status:
            QR["status"] = status
    if status != "confirmed":
        if status in ("scanned", "expired") or code:
            qr_log("poll status=%s code=%s body=%s"
                   % (status, code, json.dumps(payload, ensure_ascii=False)[:400]))
        tip = {"new": "等待扫码…", "scanned": "已扫码，请在手机上点「确认」",
               "expired": "二维码已过期，点一下刷新"}.get(status, "状态：%s" % (raw or code))
        if code == 7:
            tip = "官方限流中，稍候自动重试…"
        if code == 2046:
            tip = "需要在手机上完成二次验证"
        return {"status": status, "msg": tip, "ok": False, "raw": raw, "code": code}

    # 已确认 → 官方常规不给 Cookie，先跟一跳 redirect 试收，再查 jar
    qr_log("confirmed raw=%s code=%s body=%s" % (raw, code,
                                                json.dumps(payload, ensure_ascii=False)[:600]))
    _qr_follow(payload, sess)
    jar = sess["jar"]
    names = {c.name: c.value for c in jar}
    qr_log("jar keys=%s" % ",".join(sorted(names)))
    if not any(k in names for k in SID_KEYS):
        return {"status": "confirmed",
                "msg": ("手机已确认，但官方没把会话发给本机（它只存在扫码页浏览器里）。\n"
                        "改用手工 Cookie：浏览器登录汽水网页版后，把整段 Cookie 粘到"
                        "搜索框，开头写 `#登录 `。"),
                "need_cookie": True, "ok": False, "raw": raw, "code": code}
    cookie = "; ".join("%s=%s" % (c.name, c.value) for c in jar)
    info = me_info(cookie)
    if int((info or {}).get("status_code") or 0) == 1000016:
        return {"status": "confirmed", "msg": "会话已失效（官方回了 1000016），请重新扫码",
                "ok": False}
    nick = pick_nick(info)
    save_cookie(cookie, nick)
    with LOCK:
        PLAYED[:] = []                        # 换了账号，旧的行为历史别污染新画像
        _state_save()
    return {"status": "confirmed", "msg": "登录成功", "ok": True, "nick": nick}


def me_info(cookie):
    try:
        return _json(API + QR_ME + "?device_platform=web", b"{}",
                     {"Cookie": cookie, "Content-Type": "application/json; charset=utf-8",
                      "Referer": API + "/", "User-Agent": UA_QR}, "POST")
    except Exception:
        return {}


def pick_nick(data):
    for path in (("user", "nickname"), ("user", "nick_name"), ("user", "name"),
                 ("nickname",), ("account", "nickname"), ("data", "user", "nickname")):
        cur = data
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        if isinstance(cur, str) and cur.strip():
            return cur.strip()[:24]
    return ""


def cookie_from_text(text):
    """从「粘贴的一整段 Cookie」里抠出会话字段（含 sessionid 才算数）。"""
    raw = str(text or "").strip()
    if not raw:
        return ""
    pairs = []
    for part in re.split(r"[;\n]+", raw):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            pairs.append("%s=%s" % (k.strip(), v.strip()))
    joined = "; ".join(pairs)
    return joined if any(("%s=" % k) in joined for k in SID_KEYS) else ""


def verify_login():
    """明确失效(1000016)才清；网络失败一律不动，免得断网就掉登录。"""
    cookie = cookie_now()
    if not cookie:
        return False
    info = me_info(cookie)
    if not info:
        return False
    if int(info.get("status_code") or 0) == 1000016:
        forget_login()
        return False
    nick = pick_nick(info)
    if nick:
        save_cookie(cookie, nick)
    return True


# ============================================================================
# 音乐页面（沉浸式：上下滑切歌 + 逐行歌词 + 扫码登录）
# ============================================================================
# 页面只跟本机服务说话：CORS / UA 由服务端处理，页面本身不需要知道 API 地址。

MUSIC_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0a0b0d">
<title>汽水音乐</title>
<style>
:root{
  --bg:#0a0b0d; --ink:#f4f5f7; --dim:#9aa0a8; --dim2:#6b7178;
  --line:rgba(255,255,255,.10); --panel:rgba(255,255,255,.055);
  --acc:#3ddc97;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
img{max-width:100%}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);overflow:hidden;user-select:none}
#bg{position:fixed;inset:0;z-index:0;background-size:cover;background-position:center;
  filter:blur(46px) saturate(1.25) brightness(.42);transform:scale(1.25);
  transition:background-image .5s ease,opacity .5s}
#bg::after{content:"";position:absolute;inset:0;
  background:radial-gradient(120% 80% at 50% 0%,transparent,rgba(10,11,13,.55) 60%,#0a0b0d 100%)}
#app{position:relative;z-index:1;height:100%;display:flex;flex-direction:column}
header{display:flex;align-items:center;justify-content:space-between;
  padding:calc(14px + env(safe-area-inset-top)) 14px 6px;gap:8px}
.chip{display:inline-flex;align-items:center;gap:7px;flex-shrink:1;min-width:0;
  height:34px;padding:0 12px;border-radius:999px;background:var(--panel);
  border:1px solid var(--line);color:var(--ink);font-size:13px;cursor:pointer;
  backdrop-filter:blur(12px);transition:.18s;max-width:46vw}
.chip b{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chip:hover{background:rgba(255,255,255,.11)}
.chip .dot{width:6px;height:6px;border-radius:50%;background:var(--acc);
  box-shadow:0 0 8px var(--acc);flex-shrink:0}
.chip .dot.off{background:var(--dim2);box-shadow:none}
.chip svg{opacity:.65;flex-shrink:0}
#stage{flex:1;display:flex;align-items:center;justify-content:center;
  padding:8px 24px;min-height:0;min-width:0}
#card{width:100%;max-width:380px;text-align:center;min-width:0;
  transition:transform .32s cubic-bezier(.22,.61,.36,1),opacity .32s}
#card.out-up{transform:translateY(-42px) scale(.97);opacity:0}
#card.out-down{transform:translateY(42px) scale(.97);opacity:0}
#coverWrap{position:relative;width:100%;aspect-ratio:1;border-radius:20px;overflow:hidden;
  background:#15171b;box-shadow:0 26px 60px -18px rgba(0,0,0,.9),0 0 0 1px rgba(255,255,255,.07)}
#cover{width:100%;height:100%;object-fit:cover;display:block;transition:opacity .3s}
#playBig{position:absolute;inset:0;display:grid;place-items:center;cursor:pointer;
  background:rgba(0,0,0,.18);opacity:1;transition:.25s}
#playBig.hide{opacity:0;pointer-events:none}
#playBig i{width:74px;height:74px;border-radius:50%;display:grid;place-items:center;
  background:rgba(255,255,255,.92);backdrop-filter:blur(6px);
  box-shadow:0 10px 30px rgba(0,0,0,.45);transition:transform .18s}
#playBig:hover i{transform:scale(1.06)}
#playBig svg{margin-left:4px}
#meta{margin-top:26px;text-align:center}
#title{font-size:22px;font-weight:600;letter-spacing:-.01em;margin:0 0 8px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#artist{font-size:14px;color:var(--dim);margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#tagline{margin-top:10px;font-size:11px;color:var(--dim2);letter-spacing:.08em;
  font-family:ui-monospace,Consolas,monospace}
#lyrics{position:absolute;inset:0;z-index:5;display:none;
  background:linear-gradient(#0a0b0d 0%,rgba(10,11,13,.96) 18%,rgba(10,11,13,.96) 82%,#0a0b0d 100%);
  overflow-y:auto;padding:14vh 26px 30vh;text-align:center;scrollbar-width:none}
#lyrics::-webkit-scrollbar{display:none}
#lyrics.on{display:block}
#lyrics p{margin:0 0 20px;font-size:18px;line-height:1.55;color:rgba(255,255,255,.34);
  transition:color .25s,font-size .25s}
#lyrics p.on{color:#fff;font-size:20px;font-weight:500}
#lyrics .empty{color:var(--dim2);font-size:14px;margin-top:40vh}
footer{padding:4px 24px calc(18px + env(safe-area-inset-bottom))}
#bar{position:relative;height:26px;display:flex;align-items:center;cursor:pointer}
#bar .track{position:relative;width:100%;height:3px;border-radius:2px;background:rgba(255,255,255,.16)}
#bar .fill{position:absolute;left:0;top:0;bottom:0;width:0;border-radius:2px;background:var(--acc)}
#bar .knob{position:absolute;top:50%;left:0;width:10px;height:10px;margin:-5px 0 0 -5px;
  border-radius:50%;background:#fff;opacity:0;transition:opacity .2s}
#bar:hover .knob{opacity:1}
#time{display:flex;justify-content:space-between;font-size:11px;color:var(--dim2);
  font-family:ui-monospace,Consolas,monospace;margin:-2px 0 12px}
#ctrl{display:flex;align-items:center;justify-content:center;gap:26px}
.btn{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;
  background:none;border:none;color:var(--ink);cursor:pointer;transition:.16s}
.btn:hover{background:var(--panel)}
.btn:active{transform:scale(.92)}
.btn.main{width:62px;height:62px;background:#fff;color:#0a0b0d}
.btn.main:hover{background:#eef0f2}
.btn.liked{color:var(--acc)}
.btn.ghost{color:var(--dim)}
#queueHint{text-align:center;font-size:11px;color:var(--dim2);height:14px;margin-top:10px}
.sheet{position:fixed;inset:0;z-index:20;display:none;background:rgba(0,0,0,.62);
  backdrop-filter:blur(3px)}
.sheet.on{display:block}
.sheet .box{position:absolute;left:0;right:0;bottom:0;max-height:76vh;overflow-y:auto;
  background:#141619;border-radius:20px 20px 0 0;padding:18px 20px 26px;
  border-top:1px solid var(--line);animation:up .28s cubic-bezier(.22,.61,.36,1)}
@keyframes up{from{transform:translateY(100%)}to{transform:translateY(0)}}
.sheet h3{margin:2px 0 4px;font-size:16px;font-weight:600}
.sheet .hint{font-size:12.5px;color:var(--dim2);margin:0 0 16px;line-height:1.6}
.modes{display:flex;flex-wrap:wrap;gap:9px}
.modes button{height:36px;padding:0 15px;border-radius:10px;font-size:13.5px;
  background:var(--panel);border:1px solid var(--line);color:var(--ink);cursor:pointer;transition:.15s}
.modes button:hover{background:rgba(255,255,255,.11)}
.modes button.on{background:#fff;color:#0a0b0d;border-color:#fff;font-weight:500}
.modes .grp{width:100%;font-size:11px;color:var(--dim2);letter-spacing:.1em;
  margin:14px 0 2px;font-family:ui-monospace,Consolas,monospace}
#loginSheet .box{text-align:center}
#qrBox{width:216px;height:216px;margin:6px auto 14px;border-radius:16px;overflow:hidden;
  background:#fff;display:grid;place-items:center}
#qrBox img{width:100%;height:100%;object-fit:contain;display:block}
#qrTip{font-size:14px;color:var(--dim);min-height:22px;margin:0 0 6px}
#qrTip.ok{color:var(--acc);font-weight:500}
#qrRaw{font-size:11px;color:var(--dim2);font-family:ui-monospace,Consolas,monospace;
  min-height:16px;margin:0 0 14px}
.wideBtn{width:100%;height:44px;border-radius:12px;border:1px solid var(--line);
  background:var(--panel);color:var(--ink);font-size:14px;cursor:pointer;margin-top:8px}
.wideBtn:hover{background:rgba(255,255,255,.11)}
.wideBtn.primary{background:#fff;color:#0a0b0d;font-weight:500;border-color:#fff}
.wideBtn.danger{color:#ff8f8f}
#toast{position:fixed;left:50%;bottom:96px;transform:translate(-50%,14px);z-index:40;
  background:rgba(28,30,34,.96);border:1px solid var(--line);color:var(--ink);
  padding:10px 16px;border-radius:10px;font-size:13px;opacity:0;pointer-events:none;
  transition:.24s;white-space:nowrap;max-width:90vw;overflow:hidden;text-overflow:ellipsis}
#toast.on{opacity:1;transform:translate(-50%,0)}
@media (max-width:420px){#stage{padding:6px 20px}#title{font-size:20px}}
@media (min-width:900px){#card{max-width:340px}#lyrics{padding-top:12vh}}
</style>
</head>
<body>
<div id="bg"></div>
<div id="app">
  <header>
    <button class="chip" id="modeBtn">
      <span class="dot off" id="modeDot"></span>
      <b id="modeName">默认模式</b>
      <svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 4l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>
    <button class="chip" id="loginBtn">
      <span class="dot off" id="loginDot"></span>
      <b id="loginText">未登录</b>
    </button>
  </header>

  <div id="stage">
    <div id="card">
      <div id="coverWrap">
        <img id="cover" alt="">
        <div id="playBig"><i><svg width="26" height="26" viewBox="0 0 24 24"><path d="M8 5.2v13.6L19 12z" fill="#0a0b0d"/></svg></i></div>
      </div>
      <div id="meta">
        <h1 id="title">正在取推荐…</h1>
        <p id="artist"></p>
        <div id="tagline"></div>
      </div>
    </div>
    <div id="lyrics"><p class="empty">暂无歌词</p></div>
  </div>

  <footer>
    <div id="bar"><div class="track"><div class="fill" id="fill"></div></div><div class="knob" id="knob"></div></div>
    <div id="time"><span id="cur">0:00</span><span id="dur">0:00</span></div>
    <div id="ctrl">
      <button class="btn ghost" id="likeBtn" title="喜欢">
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 20s-7-4.35-7-9a4 4 0 017-2.65A4 4 0 0119 11c0 4.65-7 9-7 9z"/></svg>
      </button>
      <button class="btn" id="prevBtn" title="上一首">
        <svg width="22" height="22" viewBox="0 0 24 24"><path d="M7 5h2v14H7zM19 5.5v13L9.5 12z" fill="currentColor"/></svg>
      </button>
      <button class="btn main" id="playBtn" title="播放/暂停">
        <svg id="icoPlay" width="24" height="24" viewBox="0 0 24 24"><path d="M8 5.2v13.6L19 12z" fill="currentColor"/></svg>
        <svg id="icoPause" width="24" height="24" viewBox="0 0 24 24" style="display:none"><path d="M7 5h3.4v14H7zM13.6 5H17v14h-3.4z" fill="currentColor"/></svg>
      </button>
      <button class="btn" id="nextBtn" title="下一首">
        <svg width="22" height="22" viewBox="0 0 24 24"><path d="M15 5h2v14h-2zM5 5.5v13L14.5 12z" fill="currentColor"/></svg>
      </button>
      <button class="btn ghost" id="lyricBtn" title="歌词">
        <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M4 7h16M4 12h10M4 17h7"/></svg>
      </button>
    </div>
    <div id="queueHint">上滑切歌 · 空格播放</div>
  </footer>
</div>

<div class="sheet" id="modeSheet">
  <div class="box">
    <h3>听歌模式</h3>
    <p class="hint">未登录时按主题匹配出歌；登录后服务端会认 <code>scene_mode_id</code>，才是官方 App 里那套按场景推的流。</p>
    <div class="modes" id="modesList"></div>
  </div>
</div>

<div class="sheet" id="loginSheet">
  <div class="box">
    <h3>扫码登录汽水音乐</h3>
    <p class="hint">用手机「抖音 / 汽水音乐」扫下面的码，并在手机上点确认。登录后推荐才会按你的口味走。</p>
    <div id="qrBox"></div>
    <p id="qrTip">正在生成二维码…</p>
    <p id="qrRaw"></p>
    <button class="wideBtn" id="qrRefresh">刷新二维码</button>
    <button class="wideBtn danger" id="logoutBtn" style="display:none">退出登录</button>
  </div>
</div>

<div id="toast"></div>

<script>
const $ = s => document.querySelector(s);
const api = (p, o) => fetch(p, o).then(r => r.json());

let modes = [], curMode = localStorage.getItem('qs_mode') || '默认模式';
let queue = [], idx = -1, loading = false;
let audio = new Audio();
audio.preload = 'auto';

let lyric = [], lyricIdx = -1, liked = new Set(), logged = false, pollTimer = null;

const fmt = s => {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return m + ':' + String(r).padStart(2, '0');
};
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('on');
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('on'), 2200);
}

async function boot() {
  try {
    const b = await api('/api/bootstrap');
    modes = b.modes || [];
    logged = b.logged;
    setLogin(logged, b.nick);
    renderModes();
    if (!modes.some(m => m.name === curMode)) curMode = modes[0] ? modes[0].name : '默认模式';
    $('#modeName').textContent = curMode;
  } catch (e) { toast('服务未启动'); }
  loadFeed();
  if (/[?&]login=1/.test(location.search)) {
    $('#loginSheet').classList.add('on');
    startLogin();
  }
}

function setLogin(on, nick) {
  $('#loginDot').className = 'dot' + (on ? '' : ' off');
  $('#loginText').textContent = on ? (nick || '已登录') : '未登录';
  $('#logoutBtn').style.display = on ? 'block' : 'none';
}

function renderModes() {
  const box = $('#modesList');
  const pref = modes.filter(m => m.kind === 'preference');
  const scene = modes.filter(m => m.kind !== 'preference');
  let html = '<div class="grp">偏好</div>';
  html += pref.map(m => '<button data-m="' + m.name + '" class="' + (m.name === curMode ? 'on' : '') + '">' + m.name + '</button>').join('');
  html += '<div class="grp">场景</div>';
  html += scene.map(m => '<button data-m="' + m.name + '" class="' + (m.name === curMode ? 'on' : '') + '">' + m.name + '</button>').join('');
  box.innerHTML = html;
  box.querySelectorAll('button').forEach(b => b.onclick = () => {
    curMode = b.dataset.m;
    localStorage.setItem('qs_mode', curMode);
    $('#modeName').textContent = curMode;
    $('#modeDot').className = 'dot';
    closeSheets();
    queue = []; idx = -1; loadFeed(true);
  });
}

async function loadFeed(reset) {
  if (loading) return;
  loading = true;
  if (reset) { audio.pause(); }
  $('#queueHint').textContent = '正在取推荐…';
  try {
    const d = await api('/api/feed?mode=' + encodeURIComponent(curMode) + '&n=6');
    const list = d.list || [];
    if (!list.length) { toast('这次没取到歌，换个模式试试'); $('#queueHint').textContent = ''; return; }
    queue = queue.concat(list);
    $('#queueHint').textContent = '官方推荐流 · ' + (d.src || '');
    if (idx < 0) playAt(0);
  } catch (e) {
    toast('取歌失败');
  } finally {
    loading = false;
  }
}

async function playAt(i) {
  if (i < 0 || i >= queue.length) return;
  idx = i;
  const t = queue[i];
  $('#title').textContent = t.name;
  $('#artist').textContent = t.artist + (t.album ? ' · ' + t.album : '');
  $('#cover').src = t.cover || '';
  $('#bg').style.backgroundImage = t.cover ? 'url("' + t.cover + '")' : 'none';
  $('#fill').style.width = '0%';
  $('#cur').textContent = '0:00';
  $('#dur').textContent = fmt(t.duration);
  $('#tagline').textContent = curMode + ' · ' + (logged ? '按你的口味' : '匿名推荐');
  $('#likeBtn').classList.toggle('liked', liked.has(t.id));
  lyric = []; lyricIdx = -1;
  $('#lyrics').innerHTML = '<p class="empty">歌词加载中…</p>';
  try {
    const d = await api('/api/url?id=' + encodeURIComponent(t.id));
    if (d.error || !d.url) { toast('这首歌取不到流'); next(false); return; }
    if (d.track) {
      $('#artist').textContent = d.track.artist + (d.track.album ? ' · ' + d.track.album : '');
      if (d.track.cover && !t.cover) {
        $('#cover').src = d.track.cover;
        $('#bg').style.backgroundImage = 'url("' + d.track.cover + '")';
      }
    }
    const srcTag = d.source === '完整版' ? '完整版 · 320k'
      : (d.full === false ? '官方试听片段' : '官方音源');
    $('#tagline').textContent = curMode + ' · ' + srcTag + ' · ' + (logged ? '按你的口味' : '匿名推荐');
    lyric = d.lyric || [];
    renderLyric();
    audio.src = '/api/stream?id=' + encodeURIComponent(t.id);
    audio.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  } catch (e) { toast('网络异常'); }
  if (queue.length - idx <= 2) loadFeed(false);
}

function renderLyric() {
  if (!lyric.length) { $('#lyrics').innerHTML = '<p class="empty">暂无歌词</p>'; return; }
  $('#lyrics').innerHTML = lyric.map((l, i) => '<p data-i="' + i + '">' + l.text + '</p>').join('');
}

function setPlaying(on) {
  $('#icoPlay').style.display = on ? 'none' : 'block';
  $('#icoPause').style.display = on ? 'block' : 'none';
  $('#playBig').classList.toggle('hide', on);
}
function toggle() {
  if (!audio.src) { playAt(Math.max(idx, 0)); return; }
  if (audio.paused) audio.play().catch(() => {}); else audio.pause();
}
function next(auto) {
  const t = queue[idx];
  if (t) sendEvent(t, auto ? 'complete' : 'skip');
  if (idx + 1 < queue.length) {
    const c = $('#card');
    c.classList.add('out-up');
    setTimeout(() => { playAt(idx + 1); c.classList.remove('out-up'); }, 180);
  } else {
    loadFeed(false).then(() => {
      if (idx + 1 < queue.length) playAt(idx + 1); else toast('取不到更多了');
    });
  }
}
function prev() {
  if (audio.currentTime > 3) { audio.currentTime = 0; return; }
  if (idx > 0) playAt(idx - 1);
}
function sendEvent(t, action) {
  fetch('/api/event', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: t.id, name: t.name, action: action })
  }).catch(() => {});
}

audio.addEventListener('timeupdate', () => {
  if (!audio.duration) return;
  const p = audio.currentTime / audio.duration * 100;
  $('#fill').style.width = p + '%';
  $('#knob').style.left = p + '%';
  $('#cur').textContent = fmt(audio.currentTime);
  $('#dur').textContent = fmt(audio.duration);
  if (lyric.length) {
    let k = -1;
    for (let i = 0; i < lyric.length; i++) if (lyric[i].t <= audio.currentTime + 0.15) k = i; else break;
    if (k !== lyricIdx) {
      lyricIdx = k;
      $('#lyrics').querySelectorAll('p[data-i]').forEach(p => p.classList.toggle('on', +p.dataset.i === k));
      const el = $('#lyrics').querySelector('p[data-i="' + k + '"]');
      if (el && $('#lyrics').classList.contains('on')) {
        $('#lyrics').scrollTo({ top: el.offsetTop - $('#lyrics').clientHeight * 0.42, behavior: 'smooth' });
      }
    }
  }
});
audio.addEventListener('ended', () => next(true));
audio.addEventListener('play', () => setPlaying(true));
audio.addEventListener('pause', () => setPlaying(false));
audio.addEventListener('error', () => { toast('播放失败，跳到下一首'); setTimeout(() => next(false), 600); });

$('#bar').addEventListener('click', e => {
  if (!audio.duration) return;
  const r = e.currentTarget.getBoundingClientRect();
  audio.currentTime = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * audio.duration;
});

let ty = null, tx = null;
const stage = $('#stage');
stage.addEventListener('touchstart', e => { ty = e.touches[0].clientY; tx = e.touches[0].clientX; }, { passive: true });
stage.addEventListener('touchend', e => {
  if (ty === null) return;
  const dy = e.changedTouches[0].clientY - ty, dx = e.changedTouches[0].clientX - tx;
  if (Math.abs(dy) > 60 && Math.abs(dy) > Math.abs(dx)) { dy < 0 ? next(false) : prev(); }
  ty = null;
}, { passive: true });

let wheelLock = 0;
stage.addEventListener('wheel', e => {
  e.preventDefault();
  const now = Date.now();
  if (now - wheelLock < 620) return;
  if (Math.abs(e.deltaY) < 24) return;
  wheelLock = now;
  e.deltaY > 0 ? next(false) : prev();
}, { passive: false });

document.addEventListener('keydown', e => {
  if (e.code === 'Space') { e.preventDefault(); toggle(); }
  if (e.code === 'ArrowDown' || e.code === 'ArrowRight') next(false);
  if (e.code === 'ArrowUp' || e.code === 'ArrowLeft') prev();
  if (e.code === 'Escape') closeSheets();
});

$('#playBig').onclick = toggle;
$('#playBtn').onclick = toggle;
$('#nextBtn').onclick = () => next(false);
$('#prevBtn').onclick = prev;
$('#likeBtn').onclick = () => {
  const t = queue[idx]; if (!t) return;
  if (liked.has(t.id)) liked.delete(t.id); else { liked.add(t.id); sendEvent(t, 'like'); }
  $('#likeBtn').classList.toggle('liked', liked.has(t.id));
  toast(liked.has(t.id) ? '已喜欢' : '取消喜欢');
};
$('#lyricBtn').onclick = () => $('#lyrics').classList.toggle('on');
$('#lyrics').onclick = () => $('#lyrics').classList.remove('on');

$('#modeBtn').onclick = () => { $('#modeSheet').classList.add('on'); };
$('#loginBtn').onclick = () => { $('#loginSheet').classList.add('on'); startLogin(); };
document.querySelectorAll('.sheet').forEach(s => s.addEventListener('click', e => {
  if (e.target === s) closeSheets();
}));
function closeSheets() {
  document.querySelectorAll('.sheet').forEach(s => s.classList.remove('on'));
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}
$('#qrRefresh').onclick = () => startLogin(true);

async function startLogin(force) {
  clearInterval(pollTimer);
  $('#qrTip').textContent = '正在生成二维码…';
  $('#qrTip').className = '';
  $('#qrRaw').textContent = '';
  $('#qrBox').innerHTML = '';
  const d = await api('/api/login/qr' + (force ? '?f=1' : ''));
  if (d.error) { $('#qrTip').textContent = d.error; return; }
  $('#qrBox').innerHTML = '<img src="' + d.png + '" alt="二维码">';
  $('#qrTip').textContent = '用手机扫码，然后点确认';
  pollTimer = setInterval(poll, 2000);
}
async function poll() {
  if (!$('#loginSheet').classList.contains('on')) { clearInterval(pollTimer); return; }
  const d = await api('/api/login/poll');
  $('#qrTip').textContent = d.msg || '';
  $('#qrTip').className = d.ok ? 'ok' : '';
  $('#qrRaw').textContent = d.raw ? ('官方返回 status=' + d.raw + (d.code ? ' · error_code=' + d.code : '')) : '';
  if (d.ok) {
    clearInterval(pollTimer);
    setLogin(true, d.nick);
    toast('登录成功 · 推荐已切到你的口味');
    setTimeout(() => { closeSheets(); queue = []; idx = -1; loadFeed(true); }, 900);
  }
}
$('#logoutBtn').onclick = async () => {
  await api('/api/logout', { method: 'POST' });
  setLogin(false, '');
  toast('已退出登录');
  closeSheets();
  queue = []; idx = -1; loadFeed(true);
};
</script>
</body>
</html>
"""


# 极简扫码页：点「扫码登录」直接弹这个，只有二维码，不会跟播放器首页混在一起。
# （旧做法是打开 /?login=1，宿主 WebView 常把 query 丢掉，用户看到的是封面海报。）
QR_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>扫码登录 · 汽水音乐</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%;margin:0}
body{
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;
  background:radial-gradient(120% 80% at 50% 0%,#1d2130 0%,#0b0d12 60%,#07080b 100%);
  color:#eef1f7;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  padding:16px;text-align:center;overflow:auto;
}
h1{margin:0;font-size:18px;font-weight:600;letter-spacing:.4px}
.sub{margin:0;font-size:12px;color:#8e96a8;line-height:1.5}
.card{
  width:min(66vw,300px);max-height:56vh;aspect-ratio:1;border-radius:16px;background:#fff;
  display:flex;align-items:center;justify-content:center;padding:10px;
  box-shadow:0 16px 40px rgba(0,0,0,.55);
}
.card img{width:100%;height:100%;object-fit:contain;border-radius:10px;display:block}
.card.dim{opacity:.25;filter:blur(4px)}
.status{min-height:22px;font-size:14px;color:#b9c0d0}
.status.ok{color:#3ad07f;font-weight:600}
.status.warn{color:#ffb454}
.btn{
  appearance:none;border:1px solid #333a4b;background:#1a1f2b;color:#dfe4ee;
  height:40px;padding:0 20px;border-radius:999px;font-size:14px;cursor:pointer;
}
.btn:active{transform:scale(.97)}
.hint{font-size:12px;color:#5d6478;line-height:1.7;max-width:320px}
</style></head>
<body>
<h1>扫码登录汽水音乐</h1>
<p class="sub">用手机「汽水音乐」或「抖音」扫一下</p>
<div class="card" id="card"><img id="qr" alt="二维码" src="/qrs.png"></div>
<div class="status" id="st">二维码加载中…</div>
<button class="btn" id="rf">刷新二维码</button>
<p class="hint">扫码后在手机上点「确认」。登录成功这一页会变绿，直接返回就行。</p>
<script>
const $=s=>document.querySelector(s);
let timer=null, done=false;
function paint(txt,cls){ const st=$('#st'); st.textContent=txt; st.className='status'+(cls?' '+cls:''); }
async function refresh(force){
  paint('二维码加载中…');
  $('#card').classList.remove('dim');
  $('#qr').src='/qrs.png?f='+(force?1:0)+'&t='+Date.now();
  if(done) return;
  try{
    const r=await fetch('/api/login/poll',{cache:'no-store'});
    const d=await r.json();
    if(d.status==='confirmed'&&d.ok){ success(d); return; }
    if(d.status==='expired'){ paint('二维码已过期，点下面刷新', 'warn'); $('#card').classList.add('dim'); }
    else if(d.status==='scanned'){ paint(d.msg||'已扫码，请在手机上点「确认」'); }
    else paint('等待扫码…');
  }catch(e){ paint('等待扫码…'); }
}
function success(d){
  done=true; clearInterval(timer);
  $('#card').classList.add('dim');
  paint('✓ 登录成功'+(d.nick?' · '+d.nick:'')+'，窗口即将关闭','ok');
  $('#rf').textContent='可以返回了';
  // 内嵌小窗一般支持 window.close()；不支持就退化成「后退」。
  setTimeout(function(){
    try{ window.close(); }catch(e){}
    setTimeout(function(){
      try{ history.length>1 ? history.back() : null; }catch(e){}
    },300);
  },1200);
}
$('#rf').onclick=()=>{ if(done) return; done=false; refresh(1); };
refresh(0);
timer=setInterval(refresh,2200);
window.addEventListener('beforeunload',()=>clearInterval(timer));
</script>
</body></html>
"""

# 二维码 PNG 缓存：官方给的是 data:image/png;base64，转成 http 图片后
# 任何 TVBox 内核的图片加载器都能显示（列表页 vod_pic 直接就是二维码）。
QR_PNG = {"bytes": b"", "sq": b"", "at": 0.0, "expire": 0.0}


def _png_rgb(data):
    """最小 PNG 解码：只解 8bit RGB(2) / 灰度(0) 的 IHDR+IDAT，返回 (w,h,灰度列表)。
    官方二维码就是 8bit RGB 512x512；其它格式原样放行，不做裁边。"""
    try:
        if data[12:16] != b"IHDR":
            return None
        w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
        if depth != 8 or ctype not in (0, 2):
            return None
        nch = 1 if ctype == 0 else 3
        idat, i = b"", 8
        while i < len(data):
            ln = struct.unpack(">I", data[i:i + 4])[0]
            if data[i + 4:i + 8] == b"IDAT":
                idat += data[i + 8:i + 8 + ln]
            i += 12 + ln
        raw = zlib.decompress(idat)
        stride = w * nch + 1
        if len(raw) != h * stride:
            return None
        px = bytearray(w * h)                      # 灰度 0~255
        prev = bytearray(w * nch)
        for y in range(h):
            row = raw[y * stride:(y + 1) * stride]
            f, cur = row[0], bytearray(row[1:])
            if f == 1:
                for x in range(nch, len(cur)):
                    cur[x] = (cur[x] + cur[x - nch]) & 0xFF
            elif f == 2:
                for x in range(len(cur)):
                    cur[x] = (cur[x] + prev[x]) & 0xFF
            elif f == 3:
                for x in range(len(cur)):
                    a = cur[x - nch] if x >= nch else 0
                    cur[x] = (cur[x] + ((a + prev[x]) >> 1)) & 0xFF
            elif f == 4:
                for x in range(len(cur)):
                    a = cur[x - nch] if x >= nch else 0
                    b, c = prev[x], (prev[x - nch] if x >= nch else 0)
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                    cur[x] = (cur[x] + pr) & 0xFF
            base = y * w
            for x in range(w):
                px[base + x] = cur[x * nch]
            prev = cur
        return w, h, px
    except Exception:
        return None


def _png_gray(w, h, px):
    """灰度像素 → 8bit RGB PNG（filter 0）。"""
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        row = bytearray()
        base = y * w
        for x in range(w):
            v = px[base + x]
            row += bytes((v, v, v))
        raw += row
    comp = zlib.compress(bytes(raw), 6)

    def chunk(tag, blob):
        c = tag + blob
        return struct.pack(">I", len(blob)) + c + struct.pack(">I", zlib.crc32(c))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


QR_CORE_N = 512                                   # QR 本体重采样分辨率


def _qr_core(raw):
    """官方二维码 → 裁掉边缘白边 → 最近邻重采样的灰度正方形 (n, n, px)。

    像素级处理，不重建 QR 网格：可扫性与官方图完全一致（网格重建试过，
    中心 logo 区的纠错余量扛不住，扫不出来）。解码失败返回 None。
    """
    got = _png_rgb(raw)
    if not got:
        return None
    w, h, px = got
    x0, x1, y0, y1 = w, 0, h, 0
    for y in range(h):
        base = y * w
        for x in range(w):
            if px[base + x] < 128:
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    if bw < 32 or bw > w or bh < 32:
        return None
    n = QR_CORE_N
    core = bytearray(b"\xff" * (n * n))
    for oy in range(n):
        srow = (y0 + bh * oy // n) * w
        orow = oy * n
        for ox in range(n):
            v = px[srow + x0 + bw * ox // n]
            core[orow + ox] = 0 if v < 128 else min(255, v * 2 // 3 + 85)
    return n, core


def _blit_gray(out, w, px, n, dx, dy, size):
    """把 n×n 的灰度核心最近邻缩放到 size×size，画到 out(w 宽) 的 (dx,dy)。"""
    for oy in range(size):
        srow = n * oy // size * n
        orow = (dy + oy) * w + dx
        for ox in range(size):
            v = px[srow + n * ox // size]
            if v < 200:
                out[orow + ox] = v


def _qr_square(raw, side=1024):
    """官方二维码 → 满幅正方形（约 4 模块静区）。弹窗 base64 用这张。"""
    core = _qr_core(raw)
    if not core:
        return raw
    n, px = core
    margin = max(int(side * 0.055), 8)
    out = bytearray(b"\xff" * (side * side))
    _blit_gray(out, side, px, n, margin, margin, side - margin * 2)
    return _png_gray(side, side, out)


def _qr_card(raw, w=900, h=1350):
    """宿主封面框是竖版海报（约 2:3），正方形码塞进去会被拉伸压扁。

    这里把码以完整正方形放中央：2:3 框无论拉伸还是留白，看到的都是
    不变形的大正方形码。列表卡片 / 详情页封面用这张。"""
    core = _qr_core(raw)
    if not core:
        return _qr_square(raw)
    n, px = core
    pad = w // 24                                 # 左右各留约 4%
    size = w - pad * 2
    dy = (h - size) // 2
    out = bytearray(b"\xff" * (w * h))
    _blit_gray(out, w, px, n, pad, dy, size)
    return _png_gray(w, h, out)


def qr_png_bytes(force=False, kind="card"):
    """二维码 PNG。kind: card=竖版卡片封面(900x1350) / square=正方形(1024)。"""
    key = "bytes" if kind == "card" else "sq"
    now = time.time()
    with QR_LOCK:
        if not force and QR_PNG[key] and now < QR_PNG["expire"] - 5:
            return QR_PNG[key]
        cached = QR["png"] if QR["png"] and now < QR["expire"] - 5 else ""
    png = cached
    if not png:
        png = (qr_new(True) or {}).get("png") or ""
    if not png.startswith("data:"):
        return b""
    try:
        body = png.split(",", 1)[1]
        raw = base64.b64decode(body + "=" * (-len(body) % 4))
    except Exception:
        return b""
    raw = _qr_card(raw) if kind == "card" else _qr_square(raw)
    with QR_LOCK:
        QR_PNG[key] = raw
        QR_PNG["at"] = now
        QR_PNG["expire"] = float(QR["expire"] or (now + 120))
    return raw


def qr_data_uri():
    """data:image/png;base64 直塞 vod_pic：本地 8788 没起来 / 端口不通时，
    卡片封面依然是二维码，不会回落成 App 图标海报。"""
    raw = qr_png_bytes(kind="card")
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii") if raw else ""


# ============================================================================
# 本机服务：页面 + 接口（网页与列表共用同一个引擎）
# ============================================================================

PAGE = {"port": 0, "srv": None, "at": 0.0}
PAGE_LOCK = threading.Lock()


class PageHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    # ---------- 工具 ----------
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    @staticmethod
    def _query(path):
        return urllib.parse.parse_qs(urllib.parse.urlparse(path).query)

    # ---------- 路由 ----------
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        q = self._query(self.path)
        if path in ("/", "/index.html", "/music"):
            return self._send(200, MUSIC_HTML, "text/html; charset=utf-8")
        if path in ("/qr", "/qr/"):
            return self._send(200, QR_HTML, "text/html; charset=utf-8")
        if path == "/qr.png":                 # 竖版卡片封面（列表/详情）
            png = qr_png_bytes(bool((q.get("f") or [""])[0]))
            if not png:
                return self._send(500, b"no qrcode", "text/plain")
            return self._send(200, png, "image/png")
        if path == "/qrs.png":                # 正方形（网页扫码页）
            png = qr_png_bytes(bool((q.get("f") or [""])[0]), kind="square")
            if not png:
                return self._send(500, b"no qrcode", "text/plain")
            return self._send(200, png, "image/png")
        if path == "/api/ping":
            return self._json({"ok": True, "logged": logged_in()})
        if path == "/api/bootstrap":
            modes = load_modes()
            return self._json({"logged": logged_in(), "nick": nick_now(),
                               "modes": [{"key": m["key"], "name": m["name"],
                                          "kind": m["kind"], "kw": m["kw"]} for m in modes]})
        if path == "/api/feed":
            key = (q.get("mode") or ["默认模式"])[0]
            try:
                n = max(1, min(20, int((q.get("n") or ["6"])[0])))
            except Exception:
                n = 6
            return self._json(build_feed(key, n))
        if path == "/api/url":
            tid = (q.get("id") or [""])[0]
            if not tid:
                return self._json({"error": "missing id"}, 400)
            return self._json(resolve(tid))
        if path == "/api/stream":
            return self._stream((q.get("id") or [""])[0])
        if path == "/api/login/qr":
            return self._json(qr_new(bool((q.get("f") or [""])[0])))
        if path == "/api/login/poll":
            return self._json(qr_poll())
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            body = {}
        if path == "/api/event":
            tid = str(body.get("id") or "")
            if tid:
                play_event(tid, str(body.get("action") or "skip"), body.get("name") or "")
            return self._json({"ok": True, "played": len(PLAYED)})
        if path == "/api/logout":
            forget_login()
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)

    # ---------- 音频代理（只给浏览器用；TVBox 播放器走直链） ----------
    def _stream(self, tid):
        if not tid:
            return self._send(404, b"no id", "text/plain")
        info = resolve(tid)
        url = info.get("url") or ""
        ctype = "audio/mpeg" if info.get("ext") == "mp3" else "audio/mp4"
        if not url:
            return self._send(404, b"no stream", "text/plain")
        rng = self.headers.get("Range")
        headers = {"User-Agent": UA, "Referer": "https://music.douyin.com/"}
        if rng:
            headers["Range"] = rng
        try:
            up = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20)
        except Exception as e:
            return self._send(502, ("upstream: %s" % e).encode(), "text/plain")
        code = getattr(up, "status", 200)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        length = up.headers.get("Content-Length")
        if length:
            self.send_header("Content-Length", str(length))
        cr = up.headers.get("Content-Range")
        if cr:
            self.send_header("Content-Range", cr)
        if not length:
            self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while True:
                chunk = up.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except Exception:
            pass
        finally:
            try:
                up.close()
            except Exception:
                pass


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("223.5.5.5", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def page_start():
    """起页面服务（0.0.0.0，手机同网可直接访问）。返回端口，失败 0。"""
    with PAGE_LOCK:
        if PAGE["srv"] is not None:
            return PAGE["port"]
        base = int(CFG.get("port") or 8788)
        for p in range(base, base + 20):
            try:
                srv = ThreadingHTTPServer(("0.0.0.0", p), PageHandler)
            except Exception:
                continue
            srv.daemon_threads = True
            PAGE["srv"], PAGE["port"], PAGE["at"] = srv, p, time.time()
            threading.Thread(target=srv.serve_forever, name="qishui-page",
                             daemon=True).start()
            return p
        return 0


def page_urls():
    """(本机地址, 局域网地址)。启动失败两个都空。"""
    port = page_start()
    if not port:
        return "", ""
    local = "http://127.0.0.1:%d" % port
    ip = lan_ip()
    return local, ("http://%s:%d" % (ip, port)) if ip else ""


# ============================================================================
# 宿主内嵌窗口（点卡片直接弹页面）
# ============================================================================

APP_PORTS = (9988, 9978, 10000)          # 宿主本地服务端口（9988 优先，其次 9978，再往后扫）
APP_DEVICE = "/device"                  # 判别用：回 Device JSON
APP_MSG = "/msg"                        # openInternalWebview
APP_STATE = {"port": 0, "at": 0.0}
APP_LOCK = threading.RLock()


def _app_port():
    """探测宿主本地服务端口（0 = 非此 App / 服务没起）。命中缓存 300s，未命中 20s。"""
    now = time.time()
    with APP_LOCK:
        port, at = int(APP_STATE["port"] or 0), float(APP_STATE["at"] or 0)
        if port and now - at < 300:
            return port
        if not port and now - at < 20:
            return 0
    hit = {"port": 0}
    hit_lock = threading.Lock()

    def probe(p):
        if hit["port"]:
            return
        # 1) /msg 存在（405/400 说明路由在，只是方法不对）→ 就是宿主
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d%s" % (p, APP_MSG), timeout=0.35) as r:
                if getattr(r, "status", 0) in (200, 400, 405):
                    with hit_lock:
                        hit["port"] = hit["port"] or p
                    return
        except urllib.error.HTTPError as e:
            if e.code in (400, 405):
                with hit_lock:
                    hit["port"] = hit["port"] or p
                return
        except Exception:
            pass
        # 2) 台式 TVBox 的 /device
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d%s" % (p, APP_DEVICE), timeout=0.35) as r:
                text = r.read(600).decode("utf-8", "replace")
            if r.status == 200 and '"name"' in text:
                with hit_lock:
                    hit["port"] = hit["port"] or p
        except Exception:
            pass

    order = [APP_PORTS[0], APP_PORTS[1]] + list(range(APP_PORTS[1] + 1, APP_PORTS[2]))
    probe(order[0])
    if not hit["port"]:
        probe(order[1])
    if not hit["port"]:
        threads = [threading.Thread(target=probe, args=(p,), daemon=True)
                   for p in order[2:]]
        for t in threads:
            t.start()
        for t in threads:
            t.join(0.5)
    with APP_LOCK:
        APP_STATE["port"], APP_STATE["at"] = int(hit["port"] or 0), time.time()
    return int(hit["port"] or 0)


def _app_call(path, payload, timeout=2.5):
    """给宿主发一条 action，返回 (ok, status, body)。"""
    port = _app_port()
    if not port:
        return False, 0, ""
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data,
                                     headers={"Content-Type": "application/json; charset=utf-8"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = getattr(r, "status", 200)
            body = r.read(300).decode("utf-8", "replace")
        return status == 200, status, body
    except Exception:
        return False, 0, ""


OPEN = {"ok": False, "at": 0.0, "url": "", "mode": ""}


# ---------------------------------------------------------------------------
# 宿主 UI（无名影视 bridge 的 /hook/ui 协议）。
# 摸鱼网盘登录那个「原生小窗」就是走这里：POST dialog 事件（images=纯 base64
# PNG，不带 data: 前缀），关窗用 dismiss + 同一 dialog id，提示用 toast。
# py 源被 bridge.py 进程内加载，base.spider.PROXY_PORT 就是 bridge 端口。
# ---------------------------------------------------------------------------

QR_DIALOG_ID = "qs_qr"


def _bridge_port():
    try:
        import base.spider as _bs
        return int(getattr(_bs, "PROXY_PORT", 0) or 0)
    except Exception:
        return 0


def ui_send(event, timeout=3.0):
    port = _bridge_port()
    if not port:
        return False
    try:
        data = json.dumps(event, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:%d/hook/ui" % port, data=data,
                                     headers={"Content-Type": "application/json; charset=utf-8"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return getattr(r, "status", 200) == 200
    except Exception:
        return False


def ui_toast(msg):
    try:
        return ui_send({"kind": "toast", "msg": str(msg)})
    except Exception:
        return False


def ui_qr_window(png_b64, texts):
    """弹原生扫码小窗（与网盘登录同一通道），登录成功自动关窗 + Toast。"""
    if not png_b64:
        return False
    did = QR_DIALOG_ID
    ok = ui_send({"kind": "dialog", "id": did, "dialog": did,
                  "title": "扫码登录汽水音乐",
                  "texts": [str(t) for t in (texts or [])],
                  "images": [png_b64], "buttons": []})
    if not ok:
        return False

    def waiter():
        t0 = time.time()
        while time.time() - t0 < 300:
            time.sleep(1.2)
            try:
                if logged_in():
                    ui_send({"kind": "dismiss", "dialog": did})
                    nick = nick_now()
                    ui_toast("汽水音乐登录成功" + ((" · " + nick) if nick else ""))
                    return
            except Exception:
                pass
    threading.Thread(target=waiter, name="qishui-qr-watch", daemon=True).start()
    return True


# ---------------------------------------------------------------------------
# Android 原生小窗：AlertDialog + WebView，登录成功自动消失
# （Windows 版没有 java 桥，会直接跳过走下面的 HTTP 通道）
# ---------------------------------------------------------------------------

def _android_activity():
    """从 ActivityThread 里捞出当前没 paused 的 Activity。"""
    try:
        from java import jclass
    except Exception:
        return None
    try:
        AT = jclass("java.lang.Class").forName("android.app.ActivityThread")
        cur = AT.getMethod("currentActivityThread").invoke(None)
        f = AT.getDeclaredField("mActivities")
        f.setAccessible(True)
        map_obj = f.get(cur)
        values = map_obj.values().toArray() if hasattr(map_obj, "values") else map_obj.toArray()
        for rec in values:
            rc = rec.getClass()
            pf = rc.getDeclaredField("paused")
            pf.setAccessible(True)
            if not pf.getBoolean(rec):
                af = rc.getDeclaredField("activity")
                af.setAccessible(True)
                act = af.get(rec)
                if act:
                    return act
    except Exception:
        pass
    return None


def _android_run(act, fn):
    """把 fn 扔到 UI 线程执行。"""
    try:
        from java import jclass, dynamic_proxy
    except Exception:
        return False
    try:
        base = dynamic_proxy(jclass("java.lang.Runnable"))

        class _Run(base):
            def run(self):
                try:
                    self._fn()
                except Exception:
                    pass
        r = _Run()
        r._fn = fn
        act.getWindow().getDecorView().post(r)
        return True
    except Exception:
        return False


def _android_qr_window(url, timeout=240):
    """弹一个原生小窗显示二维码；登录成功后台线程负责关掉它。

    返回 True 表示小窗真的弹出来了。
    """
    act = _android_activity()
    if not act:
        return False
    state = {"dialog": None, "closed": False}

    def build():
        try:
            from java import jclass
        except Exception:
            return
        try:
            WebView = jclass("android.webkit.WebView")
            LinearLayout = jclass("android.widget.LinearLayout")
            Builder = jclass("android.app.AlertDialog$Builder")
            TypedValue = jclass("android.util.TypedValue")
            lp = jclass("android.view.ViewGroup$LayoutParams")
            dp = int(TypedValue.applyDimension(
                1, 6.0, act.getResources().getDisplayMetrics()))
            wv = WebView(act)
            st = wv.getSettings()
            st.setJavaScriptEnabled(True)
            st.setDomStorageEnabled(True)
            try:
                st.setMediaPlaybackRequiresUserGesture(False)
            except Exception:
                pass
            wv.loadUrl(url)
            box = LinearLayout(act)
            box.setOrientation(1)
            box.setPadding(dp, dp, dp, dp)
            box.addView(wv)
            b = Builder(act)
            b.setTitle("扫码登录汽水音乐")
            b.setView(box)
            dlg = b.create()
            dlg.setCanceledOnTouchOutside(False)
            dlg.show()
            state["dialog"] = dlg
            try:                     # 宽 82% 屏宽，高自适应
                dm = act.getResources().getDisplayMetrics()
                dlg.getWindow().setLayout(int(dm.widthPixels * 0.82),
                                          int(dm.heightPixels * 0.72))
            except Exception:
                pass
        except Exception:
            state["closed"] = True

    if not _android_run(act, build):
        return False
    time.sleep(0.6)                  # 等 dialog 真正起来
    if state["dialog"] is None:
        return False

    def waiter():
        t0 = time.time()
        while time.time() - t0 < timeout and not state["closed"]:
            time.sleep(1.2)
            if logged_in():
                dlg = state["dialog"]
                state["closed"] = True

                def close():
                    try:
                        dlg.dismiss()
                    except Exception:
                        pass
                _android_run(act, close)
                break
    threading.Thread(target=waiter, name="qishui-qr-close", daemon=True).start()
    return True


def open_window(url):
    """打开 App 内小窗（优先原生 Dialog，其次宿主 action）。"""
    url = str(url or "")
    if not url.startswith(("http://", "https://")):
        return False
    # 1) Android 原生小窗：最像「摸鱼网盘登录」那种弹窗，且能自己关
    try:
        if _android_qr_window(url):
            OPEN.update({"ok": True, "at": time.time(), "url": url, "mode": "android"})
            return True
    except Exception:
        pass
    # 2) 宿主提供的 openInternalWebview（CatPaw / 桌面版）
    payload = {"action": "openInternalWebview", "opt": {"url": url}}
    ok, status, body = _app_call(APP_MSG, payload)
    if ok and ("error" not in body.lower()):
        OPEN.update({"ok": True, "at": time.time(), "url": url, "mode": "app"})
        return True
    OPEN.update({"ok": False, "at": time.time(), "url": url, "mode": ""})
    return False


# ============================================================================
# Spider
# ============================================================================

def _pack(kind, value):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return kind + ":" + base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _unpack(value, kind):
    text = str(value or "")
    prefix = kind + ":"
    if not text.startswith(prefix):
        return None
    body = text[len(prefix):]
    try:
        return json.loads(base64.urlsafe_b64decode(
            (body + "=" * (-len(body) % 4)).encode("utf-8")).decode("utf-8"))
    except Exception:
        return None


def _card(t):
    """track → TVBox 卡片"""
    if not t or not t.get("id"):
        return None
    remark = t.get("artist") or "汽水音乐"
    if t.get("duration"):
        remark += " · %d:%02d" % (t["duration"] // 60, t["duration"] % 60)
    return {"vod_id": _pack("t", {"i": t["id"], "n": t.get("name") or "",
                                 "r": t.get("artist") or ""}),
            "vod_name": t.get("name") or "未知歌曲",
            "vod_pic": t.get("cover") or ICON,
            "vod_remarks": remark[:60]}


def _episode(t):
    """track → 播放地址里的一段（标题$id）"""
    return "%s$%s" % (str(t.get("name") or "歌曲").replace("$", " ").replace("#", " "),
                      _pack("m", {"i": t["id"], "n": t.get("name") or "",
                                  "r": t.get("artist") or ""}))


class Spider(BaseSpider):
    def __init__(self):
        self._cfg = {}

    def init(self, extend=""):
        try:
            cfg = json.loads(extend) if isinstance(extend, str) and extend.strip() else extend
        except Exception:
            cfg = {}
        self._cfg = cfg if isinstance(cfg, dict) else {}
        CFG["login"] = _flag(self._cfg, "login", True)
        CFG["page"] = _flag(self._cfg, "page", True)
        try:
            CFG["port"] = int(self._cfg.get("port") or 8788)
        except Exception:
            CFG["port"] = 8788
        try:
            CFG["mode_count"] = max(20, min(200, int(self._cfg.get("mode_count") or 50)))
        except Exception:
            CFG["mode_count"] = 50
        _state_load()
        try:
            load_modes()                      # 预热模式墙，首屏少等一次网络
        except Exception:
            pass
        if CFG["page"]:
            try:
                page_start()                  # 页面服务随源启动，卡片点开就是现成的
            except Exception:
                pass

    def getName(self):
        return "汽水音乐"

    # ------------------------------------------------------------------ 首页
    def homeContent(self, filter):
        # 分类里只放「听歌模式 / 登录」：音乐页面是扫码登录的载体，
        # 单独挂一个分类只会让首页多一层没必要的入口。
        classes = [{"type_id": "mode", "type_name": "听歌模式"}]
        if CFG["login"]:
            classes.append({"type_id": "login", "type_name": "登录"})
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        try:
            feed = build_feed("默认模式", 10)
            cards = [c for c in (_card(t) for t in feed["list"]) if c]
            return {"list": cards}
        except Exception:
            return {"list": []}

    # ------------------------------------------------------------------ 分类
    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or "")
        page = max(1, int(pg or 1))
        try:
            if tid == "mode":
                cards = []
                for m in load_modes():
                    cards.append({"vod_id": _pack("m", {"k": m["key"], "n": m["name"]}),
                                  "vod_name": m["name"],
                                  "vod_pic": ICON,
                                  "vod_remarks": ("官方场景 · 登录后按场景推"
                                                  if m["kind"] == "scene" else "官方个性化队列")})
                return _result(cards, page)
            if tid == "login":
                if logged_in():
                    nick = nick_now() or "汽水用户"
                    cards = [{"vod_id": _pack("l", {"k": "info"}),
                              "vod_name": "已登录：" + nick, "vod_pic": ICON,
                              "vod_remarks": "点开看状态 / 退出登录"},
                             {"vod_id": _pack("l", {"k": "logout"}),
                              "vod_name": "退出登录", "vod_pic": ICON,
                              "vod_remarks": "清掉本机登录态，回到匿名推荐"}]
                else:
                    # 卡片封面直接给二维码：列表里就能扫，不必先点进详情页。
                    # 正方形满幅大图；本地服务不通时用 data URI 兜底，不再回落海报
                    local, _lan = page_urls()
                    uri = qr_data_uri()
                    pic = (qr_url(local) if (local and uri) else uri) or ICON
                    cards = [{"vod_id": _pack("l", {"k": "qr"}),
                              "vod_name": "扫码登录", "vod_pic": pic,
                              "vod_remarks": ""}]      # remarks 会以绿字盖在封面底部，遮住码，留空
                return _result(cards, page)
            # 其余 tid 视为「听歌模式名」→ 直接出歌
            feed = build_feed(tid, CFG["mode_count"])
            cards = [c for c in (_card(t) for t in feed["list"]) if c]
            return _result(cards, page, more=bool(cards))
        except Exception:
            return _result([], page)

    # ------------------------------------------------------------------ 详情
    def detailContent(self, ids):
        value = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
        try:
            info = _unpack(value, "m")
            if info:
                return {"list": [_mode_detail(info)], "parse": 0, "jx": 0}
            info = _unpack(value, "l")
            if info:
                return {"list": [_login_detail(info)], "parse": 0, "jx": 0}
            info = _unpack(value, "p")
            if info:
                return {"list": [_page_detail()], "parse": 0, "jx": 0}
            info = _unpack(value, "t")
            if info:
                return {"list": [_track_detail(info)], "parse": 0, "jx": 0}
            return {"list": [_track_detail({"i": value})], "parse": 0, "jx": 0}
        except Exception:
            return {"list": [_track_detail({"i": value})], "parse": 0, "jx": 0}

    # ------------------------------------------------------------------ 搜索
    def searchContent(self, key, quick=False, pg="1"):
        word = str(key or "").strip()
        low = word.lower()
        if low.startswith("#"):
            return _command_result(word)
        try:
            cards = [c for c in (_card(t) for t in search_tracks(word, 40)) if c]
            return _result(cards, int(pg or 1))
        except Exception:
            return _result([], int(pg or 1))

    # ------------------------------------------------------------------ 播放
    def playerContent(self, flag, id, vipFlags=None):
        value = str(id or "")
        prefer_alt = False
        info = None
        try:
            if value.startswith("k:"):
                info, prefer_alt = _unpack(value, "k"), True
            elif value.startswith("m:"):
                info = _unpack(value, "m")
            elif value.startswith("a:"):
                parts = value.split(":", 2)
                info = {"i": parts[1] if len(parts) > 1 else ""}
                prefer_alt = len(parts) > 2 and parts[2] == "alt"
            elif value.startswith("http://") or value.startswith("https://"):
                return {"parse": 0, "jx": 0, "url": value,
                        "header": {"User-Agent": UA, "Referer": "https://music.douyin.com/"}}
            else:
                info = {"i": value}
        except Exception:
            info = {"i": value}
        info = info or {}
        tid = str(info.get("i") or "")
        if not tid:
            return {"parse": 1, "jx": 0, "url": value, "header": {}}
        play_event(tid, "play", info.get("n") or "")     # 反馈进推荐队列
        try:
            res = resolve(tid, prefer_alt)
        except Exception:
            res = {}
        url = str(res.get("url") or "")
        if not url:
            return {"parse": 1, "jx": 0, "url": value, "header": {}}
        # 直链 + music_player:1，见文件头「不出声」两条教训
        return {"parse": 0, "jx": 0, "url": url, "music_player": 1,
                "header": {"User-Agent": UA, "Referer": "https://music.douyin.com/"}}

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, params):
        return [404, "text/plain", b""]


# ---------------------------------------------------------------- 详情页组装

def _result(items, page=1, more=False, size=20):
    page = max(1, int(page or 1))
    return {"list": items, "page": page,
            "pagecount": page + 1 if more else page, "limit": size,
            "total": (page - 1) * size + len(items) + (size if more else 0)}


def _flag(cfg, key, default=True):
    raw = (cfg or {}).get(key, None)
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None or raw == "":
        return default
    return str(raw).strip().lower() not in ("0", "false", "off", "no")


def _mode_detail(info):
    key = str(info.get("k") or "默认模式")
    name = str(info.get("n") or key)
    feed = build_feed(key, CFG["mode_count"])
    tracks = [t for t in feed["list"] if t.get("id")]
    names = "#".join(_episode(t) for t in tracks)
    # 两条线路：官方（自动判断是否需要完整版）+ 强制 320k 完整版
    alt = "#".join("%s$%s" % (str(t.get("name") or "歌曲").replace("$", " ").replace("#", " "),
                              _pack("k", {"i": t["id"], "n": t.get("name") or "",
                                          "r": t.get("artist") or ""})) for t in tracks)
    return {"vod_id": _pack("m", info), "vod_name": name, "vod_pic": ICON,
            "vod_remarks": "%d 首 · %s" % (len(tracks), feed.get("src") or ""),
            "vod_content": ("听歌模式「%s」\n取数：%s\n\n"
                            "线路1 官方音源：能拿到完整版就用官方，只给试听片段时自动换完整版。\n"
                            "线路2 完整版 320k：优先走完整版音源。"
                            % (name, feed.get("src") or "-")),
            "vod_play_from": "官方音源$$$完整版 320k",
            "vod_play_url": (names or "暂无$") + "$$$" + (alt or "暂无$")}


def _track_detail(info):
    tid = str(info.get("i") or "")
    name = str(info.get("n") or "汽水音乐")
    artist = str(info.get("r") or "")
    if tid and not info.get("n"):
        try:
            res = resolve(tid)
            tk = res.get("track") or {}
            name = tk.get("name") or name
            artist = tk.get("artist") or artist
        except Exception:
            pass
    return {"vod_id": _pack("t", {"i": tid, "n": name, "r": artist}),
            "vod_name": name + ((" - " + artist) if artist else ""),
            "vod_pic": ICON,
            "vod_remarks": ("登录后按画像推荐" if logged_in() else "匿名推荐"),
            "vod_content": "汽水音乐 · %s" % (artist or "未知歌手"),
            "vod_play_from": "官方音源$$$完整版 320k",
            "vod_play_url": ("播放$a:%s:auto" % tid) + "$$$" + ("播放$a:%s:alt" % tid)}


def _login_detail(info):
    kind = str((info or {}).get("k") or "info")
    if kind == "logout":
        forget_login()
        return {"vod_id": _pack("l", {"k": "info"}), "vod_name": "已退出登录",
                "vod_pic": ICON,
                "vod_content": "登录态已清除，现在回到**匿名推荐**。\n返回「登录」分类可重新登录。",
                "vod_play_from": "汽水音乐", "vod_play_url": ""}
    local, lan = page_urls()
    url = (lan or local or "")
    if kind == "qr":
        base = local or lan or ""
        png = qr_png_bytes(kind="square")    # 弹窗用正方形；封面才用竖版 card
        b64 = base64.b64encode(png).decode("utf-8") if png else ""
        target = (base + "/qr") if base else ""
        # 1) 宿主 bridge 的原生小窗（摸鱼网盘登录同款通道，登录成功自动关）
        popped = ui_qr_window(b64, ["用手机「汽水音乐 / 抖音」扫一扫",
                                    "登录成功后这个窗口会自动关闭"])
        # 2) 实在不在 bridge 里（安卓 java 桥 / 桌面 /msg）再试内嵌 WebView
        if not popped and target:
            popped = open_window(target)
        pic = (qr_url(base) if (base and png) else qr_data_uri()) or ICON
        if popped:
            body = ("已弹出扫码小窗，用手机「汽水音乐 / 抖音」扫里面的二维码并点「确认」。\n\n"
                    "登录成功后小窗会自己关掉并提示昵称；返回「听歌模式」重新进一次就是登录态。")
        elif base and png:
            body = ("**用手机扫上面这张二维码**（这张图就是实时二维码，不是海报）。\n\n"
                    "扫完在手机上点「确认」，然后返回列表再进一次「登录」就是已登录状态。\n\n"
                    "也可以让手机浏览器打开：%s" % (lan or target))
        else:
            body = "页面服务没起来（端口被占用），重启一下源再试。"
        return {"vod_id": _pack("l", {"k": "qr"}), "vod_name": "扫码登录",
                "vod_pic": pic, "vod_content": body,
                "vod_play_from": "汽水音乐", "vod_play_url": ""}
    if kind == "info":
        nick = nick_now()
        state = ("已登录：%s" % nick) if logged_in() else "未登录"
        recent = ""
        try:
            path = os.path.join(os.path.dirname(_data_path()), "qishui_qr.log")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fp:
                    lines = fp.read().strip().splitlines()[-4:]
                if lines:
                    recent = "\n\n**最近扫码记录**\n" + "\n".join("- " + l for l in lines)
        except Exception:
            pass
        body = ("当前状态：**%s**\n\n"
                "登录后：官方按你的账号画像出歌（场景队列 + 个性化推荐）。\n"
                "未登录：用官方运营歌单池出歌 —— 场景同样对味，只是不针对你个人。\n\n"
                "%s%s" % (state,
                          ("页面：" + (lan or local)) if (lan or local) else "",
                          recent))
        return {"vod_id": _pack("l", {"k": "info"}), "vod_name": state,
                "vod_pic": ICON, "vod_content": body,
                "vod_play_from": "汽水音乐", "vod_play_url": ""}
    return _login_detail({"k": "info"})


def _page_detail():
    local, lan = page_urls()
    target = lan or local or ""
    popped = open_window(target) if target else False
    body = ("音乐页面：上下滑切歌、逐行歌词、右上角扫码登录、左上角 45 个听歌模式。\n\n"
            + ("已在屏幕上弹出窗口。" if popped
               else ("用浏览器打开：%s" % target if target else "页面服务没起来，检查端口是否被占用。")))
    return {"vod_id": _pack("p", {"k": "home"}), "vod_name": "音乐页面",
            "vod_pic": ICON, "vod_content": body,
            "vod_play_from": "汽水音乐", "vod_play_url": ""}


def _command_result(word):
    """搜索框当输入通道：`#登录 <Cookie>` / `#退出` / `#状态`（TVBox 唯一能打字的地方）。"""
    raw = str(word or "").strip()
    head, _, arg = raw.partition(" ")
    head = head.lower()
    title, body = "", ""
    if head in ("#登录", "#login"):
        cookie = cookie_from_text(arg)
        if cookie:
            info = me_info(cookie)
            if int((info or {}).get("status_code") or 0) == 1000016:
                title, body = "登录失败", "这段 Cookie 官方判为已失效（1000016），重新复制一份。"
            else:
                nick = pick_nick(info)
                save_cookie(cookie, nick)
                title = "登录成功" + ("：" + nick if nick else "")
                body = "登录态已保存，返回「听歌模式」重新进一次，推荐就会按你的画像走。"
        else:
            title, body = "没识别到会话", ("粘贴的串里没有 sessionid / sid_tt。\n"
                                        "用法：`#登录 sessionid=xxx; sid_tt=yyy`")
    elif head in ("#退出", "#logout"):
        forget_login()
        title, body = "已退出登录", "现在回到匿名推荐。"
    else:
        title, body = "登录态", ("已登录：%s" % (nick_now() or "汽水用户")
                                if logged_in() else "未登录（匿名推荐）")
    return {"list": [{"vod_id": _pack("l", {"k": "info"}), "vod_name": title,
                      "vod_pic": ICON, "vod_content": body,
                      "vod_play_from": "汽水音乐", "vod_play_url": ""}]}


# ============================================================================
# 自检：python 汽水音乐sky.py
# ============================================================================

def _selftest():
    t0 = time.time()
    print("=" * 60)
    print("汽水音乐 sky 源 · 自检")
    print("=" * 60)
    sp = Spider()
    sp.init("")
    print("登录态:", ("已登录 " + nick_now()) if logged_in() else "匿名")
    modes = load_modes()
    print("听歌模式: %d 个  (%.2fs)" % (len(modes), time.time() - t0))
    print("  偏好:", [m["name"] for m in modes if m["kind"] == "preference"])
    print("  场景:", [m["name"] for m in modes if m["kind"] == "scene"][:12], "...")
    for key in ("默认模式", "粤语", "助眠模式"):
        t1 = time.time()
        feed = build_feed(key, 6)
        print("\n[%s] %d 首  %.2fs  来源=%s"
              % (key, len(feed["list"]), time.time() - t1, feed["src"]))
        for t in feed["list"][:6]:
            print("   %-28s %-18s %d:%02d" % (t["name"][:26], t["artist"][:16],
                                              t["duration"] // 60, t["duration"] % 60))
    first = build_feed("默认模式", 1)["list"]
    if first:
        t2 = time.time()
        res = resolve(first[0]["id"])
        print("\n取流[%s] %.2fs → %s / %s / 覆盖 %ss(时长 %ss)%s"
              % (first[0]["name"], time.time() - t2, res.get("source"), res.get("quality"),
                 res.get("covered"), (res.get("track") or {}).get("duration"),
                 "" if res.get("full") else "  ← 片段，已尝试换完整版"))
        print("  歌词行数:", len(res.get("lyric") or []))
        print("  url:", (res.get("url") or "")[:90])
        pl = sp.playerContent("", "a:%s:auto" % first[0]["id"])
        print("  playerContent:", pl.get("parse"), pl.get("url", "")[:70],
              "music_player=", pl.get("music_player"))
    local, lan = page_urls()
    print("\n音乐页面: 本机 %s   局域网 %s" % (local or "-", lan or "-"))
    print("宿主弹窗:", "可用" if _app_port() else "未检测到（不影响页面）")
    print("\n首页分类:", [c["type_name"] for c in sp.homeContent(True)["class"]])
    print("自检完成，用时 %.2fs" % (time.time() - t0))


if __name__ == "__main__":
    _selftest()
