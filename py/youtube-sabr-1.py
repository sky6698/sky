#coding=utf-8
#!/usr/bin/python
"""0713 YouTube source with the true SABR/UMP playback line ported from youtube-sabr.py."""
import re
import os
import sys
import json
import html
import time
import base64
import hashlib
import threading
from urllib.parse import quote, unquote, parse_qs, urlencode, urlparse, urlunparse

import requests
from base.spider import Spider

sys.path.append('..')

DEBUG_LOG = '/sdcard/Download/youtube-sabr-1_debug.log'

YOUTUBE_CLASSES = [
    {'type_id': '4K', 'type_name': '4K'},
    {'type_id': 'HDR', 'type_name': 'HDR'},
    {'type_id': '自然', 'type_name': '自然'},
    {'type_id': '动画片', 'type_name': '动画片'},
    {'type_id': '短剧', 'type_name': '短剧'},
    {'type_id': '剧集', 'type_name': '剧集'},
    {'type_id': '电影', 'type_name': '电影'},
    {'type_id': '纪录片', 'type_name': '纪录片'},
    {'type_id': '放松', 'type_name': '放松'},
    {'type_id': '16K HDR', 'type_name': '16K HDR'},
    {'type_id': '科技', 'type_name': '科技'},
    {'type_id': '解说', 'type_name': '解说'},
]

CATEGORY_QUERY = {
    '动画片': '动画 国漫 anime cartoon',
    '短剧': '短剧',
    '剧集': '电视剧 剧集 drama',
    '电影': '电影 movie',
    '纪录片': '纪录片 documentary',
    '放松': '放松 冥想 自然 音乐 relax meditation nature',
    '4K': '4K video',
    'HDR': 'HDR video',
    '自然': '大自然 风景 动物 世界 nature wildlife scenery',
    '16K HDR': '16K HDR video',
    '科技': '科技 technology',
    '解说': '电影解说 故事解说',
}

CATEGORY_ALIASES = {
    '動畫片': '动画片',
    '劇集': '剧集',
    '電影': '电影',
    '紀錄片': '纪录片',
    '解說': '解说',
    'movie': '电影',
    'game': '科技',
    'documentary': '纪录片',
}


def _filter_group(key, name, pairs):
    return {
        'key': key,
        'name': name,
        'value': [{'n': '全部', 'v': ''}] + [{'n': n, 'v': v} for n, v in pairs]
    }


def _with_year(*groups):
    years = [{'n': '全部', 'v': ''}] + [{'n': str(year), 'v': str(year)} for year in range(2026, 1957, -1)]
    return [{'key': 'year', 'name': '年份', 'value': years}] + list(groups)


CATEGORY_FILTERS = {
    '动画片': _with_year(
        _filter_group('topic', '中文', [
            ('国漫', '国漫 3D 动画'), ('儿童早教', '儿童早教'), ('儿童歌曲', '儿童歌曲'),
            ('儿童音乐', '儿童音乐'), ('儿童绘画', '儿童绘画'), ('宝宝巴士', '宝宝巴士'),
            ('儿歌多多', '儿歌多多'), ('英语启蒙', '儿童英语启蒙'), ('安全教育', '儿童安全教育'),
        ]),
        _filter_group('channel', '频道', [
            ('小猪佩奇', '@PeppaPigChineseOfficial 小猪佩奇 中文'), ('CoComelon', '@CoComelon'),
            ('国漫合集', 'Anime ENG SUB 合集 国漫'), ('阅文动漫', '@yuewenanimation'),
            ('哔哩动漫', '@madebybilibili 哔哩动漫'), ('腾讯动漫', '@TencentVideoAnimation'),
            ('优酷动漫', '@youkuanimation 优酷动漫'), ('爱奇艺动漫', '@iQIYIAnime 爱奇艺动漫'),
        ])
    ),
    '短剧': _with_year(
        _filter_group('region', '地区/平台', [
            ('抖音', '抖音 短剧'), ('快手', '快手 短剧'), ('大陆', '大陆 短剧'),
            ('香港', '香港 短剧'), ('澳门', '澳门 短剧'), ('台湾', '台湾 短剧'),
            ('新加坡', '新加坡 短剧'), ('马来西亚', '马来西亚 短剧'), ('泰国', '泰国 短剧'),
            ('越南', '越南 短剧'), ('印度', '印度 短剧'), ('韩国', '韩国 短剧'),
            ('日本', '日本 短剧'), ('欧美', '欧美 短剧'), ('腾讯', '腾讯 短剧'),
            ('爱奇艺', '爱奇艺 短剧'), ('优酷', '优酷 短剧'), ('芒果', '芒果TV 短剧'), ('搜狐', '搜狐 短剧'),
        ]),
        _filter_group('topic', '题材/频道', [
            ('都市', '@Urbanshort-TV 都市 短剧'), ('爱情', '爱情 短剧'), ('复仇', '复仇 短剧'),
            ('穿越', '穿越 短剧'), ('喜剧', '喜剧 短剧'), ('奇幻', '奇幻 短剧'),
            ('九酱爱追剧', '@NineSauceDramaTV'), ('百万好剧场', '@1-pw5ox'),
            ('咖啡追剧', '@coffeedrama605'), ('斗罗短剧', '@DouluoDrama123 斗罗短剧'),
            ('嘟嘟剧场', '@DUDUJUCHANG'), ('牛牛短剧', '@niuniuduanju'),
        ])
    ),
    '剧集': _with_year(
        _filter_group('region', '中文', [
            ('华语热播', '华语热播电视剧官方频道'), ('粤剧', '粤剧 剧集'), ('TVB', '@TVB'),
            ('国剧放映社', '国剧放映社'), ('大陆', '大陆 剧集'), ('腾讯', '腾讯 剧集'),
            ('爱奇艺', '爱奇艺 剧集'), ('优酷', '优酷 剧集'), ('芒果', '芒果TV 剧集'),
            ('搜狐', '搜狐 剧集'), ('港台', '港台 剧集'), ('美国', '美国 剧集'),
            ('韩国', '韩国 剧集'), ('日本', '日本 剧集'), ('英国', '英国 剧集'),
        ]),
        _filter_group('platform', '平台', [
            ('Netflix', 'netflix drama'), ('Disney', 'disney drama'), ('Apple', 'apple drama'),
            ('Amazon', 'amazon drama'), ('HBO', 'hbo drama'),
        ])
    ),
    '电影': _with_year(
        _filter_group('region', '地区/平台', [
            ('大陆', '大陆 电影'), ('腾讯', '腾讯 电影'), ('爱奇艺', '爱奇艺 电影'),
            ('优酷', '优酷 电影'), ('芒果', '芒果TV 电影'), ('搜狐', '搜狐 电影'),
            ('港台', '港台 电影'), ('美国', '美国 movie'), ('韩国', '韩国 电影'),
            ('日本', '日本 电影'), ('英国', '英国 movie'),
        ]),
        _filter_group('platform', '平台', [
            ('YouTube Movies', 'youtube movies'), ('Netflix', 'netflix movie'), ('Disney', 'disney movie'),
            ('Apple', 'apple movie'), ('Amazon', 'amazon movie'), ('HBO', 'hbo movie'),
        ])
    ),
    '纪录片': _with_year(
        _filter_group('topic', '主题', [
            ('历史', '历史 纪录片'), ('野性', '野性 纪录片 wild documentary'),
            ('地球', '地球 纪录片 earth documentary'), ('宇宙', '宇宙 纪录片 universe documentary'),
            ('海洋', '海洋 纪录片 oceans documentary'), ('人文', '人文 纪录片'),
            ('战争', '战争 纪录片 war documentary'), ('BBC', 'BBC 纪录片 documentary'),
            ('国家地理', '国家地理 National Geographic documentary'), ('Netflix', 'netflix 纪录片 documentary'),
        ])
    ),
    '放松': [
        _filter_group('topic', '主题', [
            ('冥想', '冥想 放松 meditation relax'), ('睡眠', '睡眠 放松 sleep relax'),
            ('白噪音', '白噪音 放松 white noise'), ('自然声音', '自然 声音 放松 nature sounds'),
            ('雨声', '雨声 放松 rain sounds'), ('海浪', '海浪 放松 ocean waves'),
        ])
    ],
    '4K': [
        _filter_group('topic', '主题', [
            ('风景', '4K 风景 scenery'), ('城市', '4K 城市 city walk'), ('旅行', '4K travel'),
            ('动物', '4K wildlife animals'), ('航拍', '4K drone aerial'), ('演示片', '4K demo video'),
        ])
    ],
    'HDR': [
        _filter_group('topic', '主题', [
            ('风景', 'HDR 风景 scenery'), ('自然', 'HDR nature'), ('动物', 'HDR wildlife animals'),
            ('城市', 'HDR city'), ('演示片', 'HDR demo video'), ('放松', 'HDR relax'),
        ])
    ],
    '自然': [
        _filter_group('topic', '主题', [
            ('风景', '大自然 风景 nature scenery'), ('动物世界', '动物世界 wildlife documentary'),
            ('海洋', '海洋 自然 ocean nature'), ('森林', '森林 自然 forest nature'),
            ('鸟类', '鸟类 自然 birds nature'), ('地球', '地球 自然 earth nature'),
            ('国家地理', 'National Geographic nature wildlife'), ('BBC Earth', 'BBC Earth nature'),
        ])
    ],
    '16K HDR': [
        _filter_group('topic', '风景', [
            ('运动', 'GoPro 极限自行车 翼装飞行'), ('风景', 'hdr 大自然 风景'),
            ('Links TV', '@linksphotograph Links TV hdr'), ('放松', 'hdr 放松'),
            ('动物世界', 'hdr Carnivorous Animals 动物世界'), ('深海世界', 'hdr Invertebrate Fish 深海世界'),
            ('飞禽走兽', 'hdr Birds of Prey Birds'), ('生物世界', 'hdr Amphibians Reptiles 生物世界'),
        ])
    ],
    '科技': [
        _filter_group('topic', '主题', [
            ('AI', '人工智能 AI technology'), ('数码', '数码 科技 technology'),
            ('手机', '手机 评测 technology'), ('电脑', '电脑 科技 technology'),
            ('汽车科技', '汽车 科技 technology'), ('太空', '航天 太空 technology'),
        ])
    ],
    '解说': [
        _filter_group('channel', '频道主', [('宇哥侃故事', '@yuge'), ('零度解说', '@lingdujieshuo')])
    ],
}


def debug_log(message, data=None):
    try:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        if data is not None:
            if isinstance(data, (dict, list)):
                line += ' ' + json.dumps(data, ensure_ascii=False, default=str)
            else:
                line += ' ' + str(data)
        with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


# -------------------------
# tiny protobuf / UMP helpers
# -------------------------
def _pb_varint(value):
    value = int(value or 0)
    out = bytearray()
    while True:
        b = value & 0x7f
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _pb_key(field_no, wire_type):
    return _pb_varint((int(field_no) << 3) | int(wire_type))


def _pb_int(field_no, value):
    if value is None:
        return b''
    return _pb_key(field_no, 0) + _pb_varint(value)


def _pb_bool(field_no, value):
    return _pb_key(field_no, 0) + (b'\x01' if value else b'\x00')


def _pb_bytes(field_no, value):
    if value is None:
        return b''
    if isinstance(value, str):
        value = value.encode('utf-8')
    return _pb_key(field_no, 2) + _pb_varint(len(value)) + value


def _pb_str(field_no, value):
    if value is None or value == '':
        return b''
    return _pb_bytes(field_no, str(value).encode('utf-8'))


def _pb_msg(field_no, payload):
    if not payload:
        return b''
    return _pb_key(field_no, 2) + _pb_varint(len(payload)) + payload


def _b64url_decode(value):
    if not value:
        return None
    if isinstance(value, bytes):
        s = value
    else:
        s = str(value).encode('ascii', 'ignore')
    s += b'=' * ((4 - len(s) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(s)
    except Exception:
        try:
            return base64.b64decode(s)
        except Exception:
            return None


def _read_pb_varint(data, pos):
    shift = 0
    result = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        result |= (b & 0x7f) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
    return None, pos


def _skip_pb_value(data, pos, wire_type):
    if wire_type == 0:
        _, pos = _read_pb_varint(data, pos)
        return pos
    if wire_type == 1:
        return min(len(data), pos + 8)
    if wire_type == 2:
        size, pos = _read_pb_varint(data, pos)
        return min(len(data), pos + int(size or 0))
    if wire_type == 5:
        return min(len(data), pos + 4)
    return len(data)


def _pb_get_bytes(data, field_no):
    pos = 0
    while pos < len(data):
        key, pos = _read_pb_varint(data, pos)
        if key is None:
            break
        fn = key >> 3
        wt = key & 7
        if fn == field_no and wt == 2:
            size, pos = _read_pb_varint(data, pos)
            return data[pos:pos + int(size or 0)]
        pos = _skip_pb_value(data, pos, wt)
    return None


def _pb_get_int(data, field_no):
    pos = 0
    while pos < len(data):
        key, pos = _read_pb_varint(data, pos)
        if key is None:
            break
        fn = key >> 3
        wt = key & 7
        if fn == field_no and wt == 0:
            value, pos = _read_pb_varint(data, pos)
            return value
        pos = _skip_pb_value(data, pos, wt)
    return None


def _pb_get_str(data, field_no):
    value = _pb_get_bytes(data, field_no)
    if value is None:
        return None
    try:
        return value.decode('utf-8')
    except Exception:
        return None


UMP_MEDIA_HEADER = 20
UMP_MEDIA = 21
UMP_MEDIA_END = 22
UMP_NEXT_REQUEST_POLICY = 35
UMP_SABR_REDIRECT = 43
UMP_SABR_ERROR = 44
UMP_RELOAD_PLAYER_RESPONSE = 46
UMP_STREAM_PROTECTION_STATUS = 58


def _read_ump_varint_stream(fp):
    # 完全对齐 yt-dlp _streaming/ump.py::read_varint
    # 注意：UMP varint 不是 protobuf varint，也不是大端拼接。
    # 之前这里按“大端前导位”解析，会把 SABR 响应解析成大量 part_id=0，导致 media_len=0。
    first = fp.read(1)
    if not first:
        return -1
    prefix = first[0]
    size = 1 if prefix < 128 else 2 if prefix < 192 else 3 if prefix < 224 else 4 if prefix < 240 else 5
    result = 0
    shift = 0
    if size != 5:
        shift = 8 - size
        mask = (1 << shift) - 1
        result |= prefix & mask
    for _ in range(1, size):
        b = fp.read(1)
        if not b:
            return -1
        result |= b[0] << shift
        shift += 8
    return result


def _read_ump_varint_bytes(data, pos=0):
    """Read an UMP varint from bytes and return (value, next_pos)."""
    if pos >= len(data):
        return -1, pos
    prefix = data[pos]
    pos += 1
    size = 1 if prefix < 128 else 2 if prefix < 192 else 3 if prefix < 224 else 4 if prefix < 240 else 5
    result = 0
    shift = 0
    if size != 5:
        shift = 8 - size
        result = prefix & ((1 << shift) - 1)
    for _ in range(1, size):
        if pos >= len(data):
            return -1, pos
        result |= data[pos] << shift
        shift += 8
        pos += 1
    return result, pos


def iter_ump_parts(fp, max_parts=160):
    count = 0
    while count < max_parts:
        part_id = _read_ump_varint_stream(fp)
        if part_id < 0:
            break
        size = _read_ump_varint_stream(fp)
        if size < 0:
            break
        data = fp.read(size) or b''
        if len(data) < size:
            break
        count += 1
        yield part_id, data


def _sabr_media_key(part_data):
    """Return a short stable key for de-duplicating repeated SABR media parts."""
    if not part_data:
        return None
    return hashlib.sha1(part_data).hexdigest()


def _find_container_offset(media, content_type=None):
    ctype = (content_type or '').lower()
    candidates = []
    if 'webm' in ctype or 'matroska' in ctype or not ctype:
        candidates.append(media.find(b'\x1a\x45\xdf\xa3', 0, 128))
    if 'mp4' in ctype or not ctype:
        idx = media.find(b'ftyp', 0, 128)
        candidates.append(idx - 4 if idx >= 4 else -1)
    candidates = [x for x in candidates if x is not None and x >= 0]
    return min(candidates) if candidates else 0


def _sabr_header_format_id(header_data, fallback_itag=None):
    # yt-dlp MediaHeader.format_id is field 13. Older/minimal responses also expose itag in field 3.
    fmt = _pb_get_bytes(header_data, 13)
    if fmt:
        return fmt
    itag = _pb_get_int(header_data, 3) or fallback_itag
    return build_format_id(itag) if itag else b''


def _ticks_to_ms(ticks, timescale):
    try:
        return int(int(ticks or 0) * 1000 / int(timescale or 1000))
    except Exception:
        return 0


def _sabr_time_range_ms(header_data):
    # MediaHeader.time_range = field 15; TimeRange: start_ticks=1, duration_ticks=2, timescale=3
    tr = _pb_get_bytes(header_data, 15)
    if not tr:
        return 0, 0
    start_ticks = _pb_get_int(tr, 1) or 0
    duration_ticks = _pb_get_int(tr, 2) or 0
    timescale = _pb_get_int(tr, 3) or 1000
    return _ticks_to_ms(start_ticks, timescale), _ticks_to_ms(duration_ticks, timescale)


def build_buffered_range(format_id, start_ms=0, duration_ms=0, start_seq=None, end_seq=None):
    # BufferedRange: format_id=1, start_time_ms=2, duration_ms=3, start_segment_index=4, end_segment_index=5
    if not format_id:
        return b''
    p = _pb_msg(1, format_id)
    p += _pb_int(2, int(start_ms or 0))
    p += _pb_int(3, int(duration_ms or 0))
    if start_seq is not None:
        p += _pb_int(4, int(start_seq))
    if end_seq is not None:
        p += _pb_int(5, int(end_seq))
    return p


def build_format_id(itag, lmt=None, xtags=None):
    # yt-dlp _proto/videostreaming/format_id.py: itag=1, lmt=2, xtags=3
    p = b''
    if itag:
        p += _pb_int(1, int(itag))
    if lmt:
        try:
            p += _pb_int(2, int(lmt))
        except Exception:
            pass
    if xtags:
        p += _pb_str(3, xtags)
    return p


def build_client_info(client_info):
    # yt-dlp _proto/innertube/client_info.py
    c = client_info or {}
    p = b''
    p += _pb_str(1, c.get('hl') or 'en')
    p += _pb_str(2, c.get('gl') or 'US')
    p += _pb_str(12, c.get('deviceMake') or c.get('device_make'))
    p += _pb_str(13, c.get('deviceModel') or c.get('device_model'))
    p += _pb_str(14, c.get('visitorData') or c.get('visitor_data'))
    p += _pb_str(15, c.get('userAgent') or c.get('user_agent'))
    p += _pb_int(16, c.get('clientNameId') or c.get('client_name_id') or 1)
    p += _pb_str(17, c.get('clientVersion') or c.get('client_version'))
    p += _pb_str(18, c.get('osName') or c.get('os_name'))
    p += _pb_str(19, c.get('osVersion') or c.get('os_version'))
    sdk = c.get('androidSdkVersion') or c.get('android_sdk_version')
    if sdk:
        p += _pb_int(64, sdk)
    return p


def build_media_capabilities(client_name_id, prefer_hdr=False):
    # 对 ANDROID/IOS/ANDROID_VR 客户端，yt-dlp 会带 MediaCapabilities
    if client_name_id not in (3, 5, 28, 101):
        return b''
    p = b''
    # VideoFormatCapability: video_codec=1, efficient=2, is_10_bit_supported=15
    for codec in (2, 4, 8, 9):  # H264 VP9 AV1 H265
        p += _pb_msg(1, _pb_int(1, codec) + _pb_bool(2, True) + _pb_bool(15, True))
    # AudioFormatCapability: audio_codec=1
    for acodec in (1, 3, 9, 13):  # AAC OPUS MP3 XHEAAC
        p += _pb_msg(2, _pb_int(1, acodec))
    p += _pb_int(5, 3 if prefer_hdr else 0)
    return p


def build_client_abr_state(client_name_id=1, start_time_ms=0, prefer_hdr=False, audio_only=False):
    # ClientAbrState: player_time_ms=28, media_capabilities=38, enabled_track_types_bitfield=40,
    # drc_enabled=46, enable_voice_boost=76
    p = b''
    p += _pb_int(28, int(start_time_ms or 0))
    mc = build_media_capabilities(client_name_id, prefer_hdr=prefer_hdr)
    if mc:
        p += _pb_msg(38, mc)
    p += _pb_int(40, 1 if audio_only else 0)
    p += _pb_bool(46, True)
    p += _pb_bool(76, True)
    return p


def build_streamer_context(client_info, po_token=None, playback_cookie=None):
    # StreamerContext: client_info=1, po_token=2, playback_cookie=3
    p = b''
    p += _pb_msg(1, build_client_info(client_info))
    pot = _b64url_decode(po_token) if po_token else None
    if pot:
        p += _pb_bytes(2, pot)
    if playback_cookie:
        p += _pb_bytes(3, playback_cookie)
    return p


def build_vpabr_request(sabr_config, video_itag=None, audio_itag=None, start_time_ms=0, playback_cookie=None, initialized_format_ids=None, buffered_ranges=None):
    # VideoPlaybackAbrRequest fields used by yt-dlp:
    # client_abr_state=1, initialized_format_ids=2, buffered_ranges=3, player_time_ms=4,
    # video_playback_ustreamer_config=5, preferred_audio_format_ids=16, preferred_video_format_ids=17, streamer_context=19
    client_info = sabr_config.get('client_info') or {}
    client_name_id = client_info.get('clientNameId') or client_info.get('client_name_id') or 1
    p = b''
    p += _pb_msg(1, build_client_abr_state(client_name_id, start_time_ms, bool(sabr_config.get('prefer_hdr')), not video_itag))
    for fmt_id in initialized_format_ids or []:
        if fmt_id:
            p += _pb_msg(2, fmt_id)
    for br in buffered_ranges or []:
        if br:
            p += _pb_msg(3, br)
    p += _pb_int(4, int(start_time_ms or 0))
    ustreamer = _b64url_decode(sabr_config.get('video_playback_ustreamer_config'))
    if ustreamer:
        p += _pb_bytes(5, ustreamer)
    if audio_itag:
        p += _pb_msg(16, build_format_id(audio_itag))
    if video_itag:
        p += _pb_msg(17, build_format_id(video_itag, sabr_config.get('last_modified'), sabr_config.get('xtags')))
    p += _pb_msg(19, build_streamer_context(client_info, sabr_config.get('po_token'), playback_cookie))
    return p

class YouTubeLite:
    def __init__(self, session, headers=None, config=None):
        self.session = session
        self.headers = headers or {}
        self.config = config or {}
        self.player_cache = {}
        self.extract_cache = {}
        self.sig_plan_cache = {}
        self._n_log_seen = set()
        self.sabr_state = {}
        self.extract_cache_ttl = int(self.config.get('extract_cache_ttl') or 300)

    def extract(self, url_or_id, force_refresh=False):
        video_id = self.extract_video_id(url_or_id)
        cached = self.extract_cache.get(video_id)
        now = time.time()
        if not force_refresh and cached and cached.get('expires', 0) > now:
            self.trace('extract cache hit', {'video_id': video_id, 'ttl': int(cached.get('expires', 0) - now)})
            return cached['data']

        started = time.time()
        watch_url = f'https://www.youtube.com/watch?v={video_id}'
        self.trace('extract start', {'video_id': video_id, 'force_refresh': force_refresh})
        page_resp = self._get(watch_url)
        page = page_resp.text
        self.trace('watch page', {'status': page_resp.status_code, 'length': len(page)})

        ytcfg = self._extract_ytcfg(page) or {}
        initial_pr = self._extract_initial_player_response(page) or {}
        player_url = self._extract_player_url(page)
        api_key = ytcfg.get('INNERTUBE_API_KEY') or self._search(r'"INNERTUBE_API_KEY":"([^"]+)"', page)
        visitor_data = self._extract_visitor_data(ytcfg, initial_pr)
        sts = self._extract_signature_timestamp(video_id, player_url, ytcfg)
        self.trace('page parsed', {
            'has_ytcfg': bool(ytcfg),
            'has_initial_pr': bool(initial_pr),
            'initial_status': (initial_pr.get('playabilityStatus') or {}).get('status'),
            'initial_has_streaming': bool(initial_pr.get('streamingData')),
            'has_api_key': bool(api_key),
            'has_visitor': bool(visitor_data),
            'sts': sts,
            'player_url': player_url,
        })

        context = ytcfg.get('INNERTUBE_CONTEXT') or {
            'client': {'clientName': 'WEB', 'clientVersion': '2.20240310.01.00', 'hl': 'en', 'gl': 'US'}
        }
        responses = []
        if initial_pr:
            initial_pr['_client_name'] = 'WEB_INITIAL'
            initial_pr['_client_ua'] = self.headers.get('User-Agent') or UA
            initial_pr['_client_info'] = {'clientNameId': 1, 'clientName': 'WEB', 'clientVersion': 'initial', 'userAgent': self.headers.get('User-Agent') or UA, 'hl': 'en', 'gl': 'US', 'visitorData': visitor_data}
            responses.append(initial_pr)
        if api_key:
            api_responses = self._call_player_api(video_id, api_key, context, watch_url, visitor_data, sts)
            responses.extend([x for x in api_responses if x])

        best_pr = next((x for x in responses if (x.get('playabilityStatus') or {}).get('status') == 'OK'), initial_pr)
        status = (best_pr.get('playabilityStatus') or {}).get('status')
        streaming = best_pr.get('streamingData') or {}
        if status and status not in ('OK', 'LIVE_STREAM_OFFLINE') and not streaming:
            reason = (best_pr.get('playabilityStatus') or {}).get('reason') or status
            raise Exception(f'YouTube 不可播放: {reason}')

        details = best_pr.get('videoDetails') or {}
        formats, sabr_formats = self._extract_formats_from_responses(responses, player_url)
        result = {
            'id': video_id,
            'title': details.get('title') or video_id,
            'duration': int(details.get('lengthSeconds') or 0),
            'formats': formats,
            'sabr_formats': sabr_formats,
            'player_url': player_url,
        }
        self.extract_cache[video_id] = {'data': result, 'expires': time.time() + self.extract_cache_ttl}
        self.trace('extract complete', {
            'video_id': video_id,
            'cost_ms': int((time.time() - started) * 1000),
            'direct_formats': len(formats),
            'sabr_formats': len(sabr_formats),
            'direct_heights': sorted(set(int(x.get('height') or 0) for x in formats if x.get('vcodec') != 'none'), reverse=True)[:12],
            'sabr_heights': sorted(set(int(x.get('height') or 0) for x in sabr_formats if x.get('vcodec') != 'none'), reverse=True)[:12],
        })
        return result

    @staticmethod
    def extract_video_id(text):
        text = str(text or '').strip()
        for pattern in [
            r'(?:v=|/v/|/embed/|/shorts/|youtu\.be/)([0-9A-Za-z_-]{11})',
            r'^([0-9A-Za-z_-]{11})$',
        ]:
            m = re.search(pattern, text)
            if m:
                return m.group(1)
        raise Exception('无法识别 YouTube 视频 ID')
    def _client_name_id(self, client_name):
        return {
            'WEB': 1,
            'MWEB': 2,
            'ANDROID': 3,
            'IOS': 5,
            'TVHTML5': 7,
            'ANDROID_VR': 28,
            'WEB_EMBEDDED_PLAYER': 56,
            'WEB_REMIX': 67,
        }.get(client_name, 1)

    def _extract_visitor_data(self, ytcfg, player_response):
        return (
            self.config.get('visitor_data')
            or ytcfg.get('VISITOR_DATA')
            or (((ytcfg.get('INNERTUBE_CONTEXT') or {}).get('client') or {}).get('visitorData'))
            or ((player_response.get('responseContext') or {}).get('visitorData'))
        )

    def _extract_signature_timestamp(self, video_id, player_url, ytcfg=None):
        try:
            code = self._get_player_code(player_url)
            sts = self._search(r'(?:signatureTimestamp|sts)\s*:\s*(\d{5})', code)
            return int(sts) if sts else None
        except Exception as e:
            debug_log('sts extract error', repr(e))
            return None

    def _get_po_token(self, client_name, context='gvs'):
        tokens = self.config.get('po_token') or self.config.get('po_tokens') or {}
        if isinstance(tokens, str):
            return tokens
        if isinstance(tokens, dict):
            return tokens.get(f'{client_name}.{context}') or tokens.get(client_name) or tokens.get(context)
        return None
    def choose_playable(self, formats, quality=None):
        all_videos = [x for x in formats if x.get('vcodec') != 'none' and x.get('acodec') == 'none']
        candidates = all_videos[:]
        if quality in ('8k', '8k_hdr'):
            candidates = [x for x in candidates if int(x.get('height') or 0) >= 4320]
            if quality == '8k':
                candidates = [x for x in candidates if not self._is_hdr_video(x)]
            else:
                candidates = [x for x in candidates if self._is_hdr_video(x)]
        elif quality == '4k':
            candidates = [x for x in candidates if 2160 <= int(x.get('height') or 0) < 4320]
        elif quality == '2k':
            candidates = [x for x in candidates if 1440 <= int(x.get('height') or 0) < 2160]
        elif quality == '1080p':
            candidates = [x for x in candidates if 1000 <= int(x.get('height') or 0) < 1440]
        elif quality == 'best':
            safe_candidates = [x for x in candidates if not self._is_risky_best_video(x)]
            if safe_candidates:
                candidates = safe_candidates
        else:
            candidates = [x for x in candidates if int(x.get('height') or 0) >= 1080]

        if not candidates and quality == 'best':
            candidates = all_videos
        if not candidates:
            return None
        # 画质优先，编码顺序 VP9/HDR > H264 > AV1。保留 VP9 Profile 2 HDR，
        # 只把 AV1 放到最后，避免默认选到 itag 701/702 的超大 AV1 分段。
        candidates.sort(key=lambda x: (
            self._video_codec_priority(x),
            int(x.get('height') or 0),
            int(x.get('bitrate') or 0)
        ), reverse=True)
        selected = candidates[0]
        debug_log('video selected fast', {
            'quality': quality,
            'itag': selected.get('itag'),
            'height': selected.get('height'),
            'mime': selected.get('mimeType'),
            'codec_priority': self._video_codec_priority(selected),
            'candidates': len(candidates),
            'probe_skipped': True,
        })
        return selected

    def _video_codec_priority(self, item):
        mime = (item.get('mimeType') or '').lower()
        codecs = (item.get('codecs') or '').lower()
        if 'vp9.2' in mime or 'vp09.02' in codecs:
            return 4
        if 'vp9' in mime or 'vp09' in codecs:
            return 3
        if 'avc' in codecs or 'h264' in codecs:
            return 2
        if 'av01' in codecs:
            return 1
        return 0

    def _is_risky_best_video(self, item):
        codecs = (item.get('codecs') or '').lower()
        return 'av01' in codecs

    def choose_video_tracks(self, formats, quality=None, protocol=None):
        videos = [x for x in formats if x.get('vcodec') != 'none' and x.get('acodec') == 'none' and (not protocol or x.get('protocol') == protocol)]
        if quality == 'best':
            capped = [x for x in videos if int(x.get('height') or 0) <= 2160]
            videos = capped or videos
        elif quality in ('8k', '8k_hdr'):
            videos = [x for x in videos if int(x.get('height') or 0) >= 4320]
        elif quality == '4k':
            videos = [x for x in videos if 2160 <= int(x.get('height') or 0) < 4320]
        elif quality == '2k':
            videos = [x for x in videos if 1440 <= int(x.get('height') or 0) < 2160]
        elif quality == '1080p':
            videos = [x for x in videos if 1000 <= int(x.get('height') or 0) < 1440]
        sdr = [x for x in videos if not self._is_hdr_video(x)]
        hdr = [x for x in videos if self._is_hdr_video(x)]
        sort_key = lambda x: (
            int(x.get('height') or 0),
            self._video_codec_priority(x),
            int(x.get('bitrate') or 0)
        )
        sdr.sort(key=sort_key, reverse=True)
        hdr.sort(key=sort_key, reverse=True)
        tracks = []
        if sdr:
            item = sdr[0].copy()
            item['track_name'] = 'SDR'
            item['is_hdr'] = False
            tracks.append(item)
        if hdr:
            item = hdr[0].copy()
            item['track_name'] = 'HDR'
            item['is_hdr'] = True
            tracks.append(item)
        if not tracks:
            item = self.choose_playable(videos, quality)
            if item:
                item = item.copy()
                item['track_name'] = 'HDR' if self._is_hdr_video(item) else 'SDR'
                item['is_hdr'] = self._is_hdr_video(item)
                tracks.append(item)
        debug_log('video tracks selected', [{'name': x.get('track_name'), 'itag': x.get('itag'), 'height': x.get('height'), 'codecs': x.get('codecs')} for x in tracks])
        return tracks

    def _is_hdr_video(self, item):
        mime = (item.get('mimeType') or '').lower()
        codecs = (item.get('codecs') or '').lower()
        color = item.get('colorInfo') or {}
        color_text = json.dumps(color, ensure_ascii=False).lower()
        hdr_markers = ('smpte2084', 'arib-std-b67', 'bt2020', 'hdr10', 'hlg', 'pq')
        return (
            'vp9.2' in mime
            or 'vp09.02' in codecs
            or bool(color.get('hdrMetadataInfo') or color.get('hdrMetadata'))
            or any(marker in color_text for marker in hdr_markers)
        )

    def choose_audio(self, formats, protocol=None, same_client=None):
        candidates = [
            x for x in formats
            if x.get('acodec') != 'none' and x.get('vcodec') == 'none'
            and (not protocol or x.get('protocol') == protocol)
        ]
        if same_client:
            same = [x for x in candidates if x.get('client') == same_client]
            if same:
                candidates = same
        if not candidates:
            return None
        candidates.sort(key=lambda x: (1 if x.get('ext') == 'mp4' else 0, int(x.get('bitrate') or 0)), reverse=True)
        selected = candidates[0]
        debug_log('audio selected fast', {
            'itag': selected.get('itag'), 'mime': selected.get('mimeType'),
            'bitrate': selected.get('bitrate'), 'protocol': selected.get('protocol'),
            'client': selected.get('client'), 'probe_skipped': True,
        })
        return selected

    def _probe_format(self, item):
        if item.get('protocol') == 'sabr':
            return False, 'skip-sabr-probe'
        try:
            headers = self.headers.copy()
            headers.update(item.get('headers') or {})
            headers['Range'] = 'bytes=0-1'
            r = self.session.get(item.get('url'), headers=headers, stream=True, timeout=10)
            if r.url and r.url != item.get('url'):
                item['url'] = r.url
                item['redirected'] = True
                debug_log('probe redirected url', self._url_summary(r.url))
            status_code = r.status_code
            r.close()
            return status_code in (200, 206), status_code
        except Exception as e:
            return False, repr(e)

    def choose_best_video_audio(self, formats):
        videos = [x for x in formats if x.get('vcodec') != 'none' and x.get('acodec') == 'none']
        audios = [x for x in formats if x.get('acodec') != 'none' and x.get('vcodec') == 'none']
        videos.sort(key=lambda x: (int(x.get('height') or 0), int(x.get('bitrate') or 0)), reverse=True)
        audios.sort(key=lambda x: int(x.get('bitrate') or 0), reverse=True)
        return (videos[0] if videos else None), (audios[0] if audios else None)

    def _url_summary(self, media_url):
        parsed = urlparse(media_url or '')
        query = parse_qs(parsed.query)
        keys = ['itag', 'mime', 'c', 'expire', 'ip', 'mip', 'source', 'requiressl', 'gir', 'clen', 'dur', 'n', 'pot', 'sig', 'lsig', 'cms_redirect']
        return {
            'host': parsed.netloc,
            'path': parsed.path,
            'len': len(media_url or ''),
            'params': {k: bool(query.get(k)) if k in ('pot', 'sig', 'lsig', 'cms_redirect') else (query.get(k, [''])[0][:80]) for k in keys if k in query}
        }

    def _get(self, url, **kwargs):
        headers = self.headers.copy()
        headers.update(kwargs.pop('headers', {}) or {})
        r = self.session.get(url, headers=headers, timeout=kwargs.pop('timeout', 15), **kwargs)
        r.raise_for_status()
        return r

    def _post_json(self, url, payload, headers=None):
        h = self.headers.copy()
        h.update({'Content-Type': 'application/json', 'Origin': 'https://www.youtube.com'})
        if headers:
            h.update({k: v for k, v in headers.items() if v})
        r = self.session.post(url, json=payload, headers=h, timeout=15)
        r.raise_for_status()
        return r.json()

    def _call_player_api(self, video_id, api_key, context, referer, visitor_data=None, sts=None):
        clients = [
            {'client': {'clientName': 'ANDROID_VR', 'clientVersion': '1.65.10', 'deviceMake': 'Oculus', 'deviceModel': 'Quest 3', 'androidSdkVersion': 32, 'userAgent': 'com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip', 'osName': 'Android', 'osVersion': '12L', 'hl': 'en', 'gl': 'US'}},
            {'client': {'clientName': 'ANDROID', 'clientVersion': '21.02.35', 'androidSdkVersion': 30, 'userAgent': 'com.google.android.youtube/21.02.35 (Linux; U; Android 11) gzip', 'osName': 'Android', 'osVersion': '11', 'hl': 'en', 'gl': 'US'}},
            {'client': {'clientName': 'IOS', 'clientVersion': '21.02.3', 'deviceMake': 'Apple', 'deviceModel': 'iPhone16,2', 'userAgent': 'com.google.ios.youtube/21.02.3 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)', 'osName': 'iPhone', 'osVersion': '18.3.2.22D82', 'hl': 'en', 'gl': 'US'}},
            context,
            {'client': {'clientName': 'MWEB', 'clientVersion': '2.20260115.01.00', 'userAgent': 'Mozilla/5.0 (iPad; CPU OS 16_7_10 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1,gzip(gfe)', 'hl': 'en', 'gl': 'US'}},
        ]
        results = []
        for ctx in clients:
            client = ctx.get('client') or {}
            client_name = client.get('clientName')
            try:
                url = f'https://www.youtube.com/youtubei/v1/player?key={api_key}&prettyPrint=false'
                payload = {
                    'context': ctx,
                    'videoId': video_id,
                    'playbackContext': {'contentPlaybackContext': {'html5Preference': 'HTML5_PREF_WANTS', **({'signatureTimestamp': sts} if sts else {})}},
                    'contentCheckOk': True,
                    'racyCheckOk': True,
                }
                headers = {
                    'Referer': referer,
                    'X-YouTube-Client-Name': str(self._client_name_id(client_name)),
                    'X-YouTube-Client-Version': client.get('clientVersion') or '',
                }
                if visitor_data:
                    headers['X-Goog-Visitor-Id'] = visitor_data
                    client['visitorData'] = visitor_data
                client_ua = client.get('userAgent')
                if client_ua:
                    headers['User-Agent'] = client_ua
                data = self._post_json(url, payload, headers=headers)
                status = (data.get('playabilityStatus') or {}).get('status')
                sd = data.get('streamingData') or {}
                data['_client_name'] = client_name
                data['_client_ua'] = client_ua
                data['_client_info'] = {
                    'clientNameId': self._client_name_id(client_name),
                    'clientName': client_name,
                    'clientVersion': client.get('clientVersion'),
                    'userAgent': client_ua,
                    'deviceMake': client.get('deviceMake'),
                    'deviceModel': client.get('deviceModel'),
                    'androidSdkVersion': client.get('androidSdkVersion'),
                    'osName': client.get('osName'),
                    'osVersion': client.get('osVersion'),
                    'hl': client.get('hl') or 'en',
                    'gl': client.get('gl') or 'US',
                    'visitorData': visitor_data,
                }
                direct_video = [x for x in sd.get('adaptiveFormats') or [] if str(x.get('mimeType') or '').startswith('video/') and (x.get('url') or x.get('cipher') or x.get('signatureCipher'))]
                self.trace('player api client', {
                    'client': client_name,
                    'status': status,
                    'has_streaming': bool(sd),
                    'formats': len(sd.get('formats') or []),
                    'adaptive': len(sd.get('adaptiveFormats') or []),
                    'direct_video': len(direct_video),
                    'has_sabr_url': bool(sd.get('serverAbrStreamingUrl')),
                    'has_ustreamer': bool(self._traverse(data, ('playerConfig', 'mediaCommonConfig', 'mediaUstreamerRequestConfig', 'videoPlaybackUstreamerConfig'))),
                })
                if sd:
                    results.append(data)
            except Exception as e:
                self.trace('player api client error', {'client': client_name, 'error': repr(e)})
        return results

    def _normalize_format(self, fmt, player_url):
        media_url = fmt.get('url')
        if not media_url:
            cipher = fmt.get('signatureCipher') or fmt.get('cipher')
            if cipher:
                media_url = self._decrypt_signature_cipher(cipher, player_url)
        if not media_url:
            return None
        media_url = self._decrypt_nsig(media_url, player_url)
        client_name = fmt.get('_client_name')
        po_token = self._get_po_token(client_name, 'gvs') if client_name else None
        if po_token:
            sep = '&' if '?' in media_url else '?'
            media_url = f'{media_url}{sep}pot={quote(po_token)}'
        mime = fmt.get('mimeType') or ''
        ext = 'mp4' if 'mp4' in mime else 'webm' if 'webm' in mime else 'unknown'
        codecs = self._search(r'codecs="([^"]+)"', mime) or ''
        has_audio = mime.startswith('audio/') or any(x in codecs for x in ('mp4a', 'opus', 'vorbis'))
        has_video = mime.startswith('video/') or any(x in codecs for x in ('avc', 'vp9', 'av01', 'h264'))
        headers = (fmt.get('http_headers') or {}).copy()
        if fmt.get('_client_ua'):
            headers['User-Agent'] = fmt.get('_client_ua')
        return {
            'itag': fmt.get('itag'),
            'url': media_url,
            'mimeType': mime,
            'client': fmt.get('_client_name'),
            'ext': ext,
            'width': fmt.get('width') or 0,
            'height': fmt.get('height') or 0,
            'fps': fmt.get('fps') or 0,
            'bitrate': fmt.get('bitrate') or fmt.get('averageBitrate') or 0,
            'contentLength': fmt.get('contentLength'),
            'initRange': fmt.get('initRange') or {},
            'indexRange': fmt.get('indexRange') or {},
            'codecs': codecs,
            'quality': fmt.get('qualityLabel') or fmt.get('quality'),
            'colorInfo': fmt.get('colorInfo') or {},
            'vcodec': codecs if has_video else 'none',
            'acodec': codecs if has_audio else 'none',
            'headers': headers,
        }

    def _decrypt_signature_cipher(self, cipher, player_url):
        data = parse_qs(cipher)
        media_url = unquote(data.get('url', [''])[0])
        sig = unquote(data.get('s', [''])[0])
        sp = data.get('sp', ['sig'])[0]
        if not media_url:
            return ''
        if sig:
            decoded = self._decrypt_sig(sig, player_url)
            debug_log('signature cipher', {'sp': sp, 'sig_len': len(sig), 'decoded_changed': decoded != sig, 'has_player': bool(player_url)})
            sep = '&' if '?' in media_url else '?'
            media_url = f'{media_url}{sep}{sp}={quote(decoded)}'
        return media_url

    def _decrypt_sig(self, sig, player_url):
        cache_key = player_url or ''
        if cache_key in self.sig_plan_cache:
            plan = self.sig_plan_cache.get(cache_key)
            debug_log('sig plan cache', {'has_plan': bool(plan), 'plan': plan[:8] if plan else None})
        else:
            code = self._get_player_code(player_url)
            plan = self._extract_sig_plan(code)
            self.sig_plan_cache[cache_key] = plan
            debug_log('sig plan', {'code_len': len(code), 'has_plan': bool(plan), 'plan': plan[:8] if plan else None})
        if not plan:
            return sig
        arr = list(sig)
        for op, arg in plan:
            if op == 'reverse':
                arr.reverse()
            elif op in ('slice', 'splice'):
                arr = arr[int(arg):]
            elif op == 'swap' and arr:
                j = int(arg) % len(arr)
                arr[0], arr[j] = arr[j], arr[0]
        return ''.join(arr)

    def _decrypt_nsig(self, media_url, player_url):
        try:
            parsed = urlparse(media_url)
            query = parse_qs(parsed.query)
            n_value = query.get('n', [None])[0]
            if not n_value:
                return media_url
            path_match = re.search(r'/n/([^/]+)', parsed.path)
            if path_match and path_match.group(1) != n_value:
                new_path = parsed.path.replace(f"/n/{path_match.group(1)}", f"/n/{n_value}", 1)
                fixed = urlunparse(parsed._replace(path=new_path))
                debug_log('n path synced', {'old': path_match.group(1), 'new_len': len(n_value), 'changed': fixed != media_url})
                return fixed
            debug_log('n present', {'n_len': len(n_value), 'has_path_n': bool(path_match)})
            return media_url
        except Exception as e:
            debug_log('n sync error', repr(e))
            return media_url

    def _get_player_code(self, player_url):
        if not player_url:
            return ''
        if player_url in self.player_cache:
            return self.player_cache[player_url]
        if player_url.startswith('//'):
            player_url = 'https:' + player_url
        elif player_url.startswith('/'):
            player_url = 'https://www.youtube.com' + player_url
        try:
            code = self._get(player_url).text
        except Exception:
            code = ''
        self.player_cache[player_url] = code
        return code

    def _extract_sig_plan(self, code):
        if not code:
            return None
        name = None
        for pattern in [
            r'\.sig\|\|([a-zA-Z0-9_$]+)\(',
            r'"signature",\s*([a-zA-Z0-9_$]+)\(',
            r'([a-zA-Z0-9_$]+)=function\(a\)\{a=a\.split\(""\);',
        ]:
            m = re.search(pattern, code)
            if m:
                name = m.group(1)
                break
        if not name:
            return None
        body = self._extract_js_function_body(code, name)
        if not body:
            return None
        helper = self._search(r'([a-zA-Z0-9_$]+)\.[a-zA-Z0-9_$]+\(a,\d+\)', body)
        helper_map = self._extract_helper_object(code, helper) if helper else {}
        plan = []
        for part in body.split(';'):
            if 'reverse()' in part:
                plan.append(('reverse', 0))
                continue
            m = re.search(r'\.slice\((\d+)\)', part)
            if m:
                plan.append(('slice', int(m.group(1))))
                continue
            m = re.search(r'\.splice\(0,(\d+)\)', part)
            if m:
                plan.append(('splice', int(m.group(1))))
                continue
            m = re.search(r'([a-zA-Z0-9_$]+)\.([a-zA-Z0-9_$]+)\(a,(\d+)\)', part)
            if m and m.group(1) == helper:
                op = helper_map.get(m.group(2))
                if op:
                    plan.append((op, int(m.group(3))))
        return plan or None

    def _extract_helper_object(self, code, name):
        if not name:
            return {}
        m = re.search(r'var\s+' + re.escape(name) + r'=\{(.+?)\};', code, re.S) or re.search(re.escape(name) + r'=\{(.+?)\};', code, re.S)
        if not m:
            return {}
        result = {}
        for method, body in re.findall(r'([a-zA-Z0-9_$]+):function\([a-z,]+\)\{(.*?)\}', m.group(1)):
            if '.reverse(' in body:
                result[method] = 'reverse'
            elif '.splice(' in body:
                result[method] = 'splice'
            elif '.slice(' in body:
                result[method] = 'slice'
            elif 'a[0]' in body and 'length' in body:
                result[method] = 'swap'
        return result

    def _extract_n_function(self, code):
        if not code:
            return None
        name = None
        for pattern in [
            r'\.get\("n"\)\)&&\(b=([a-zA-Z0-9_$]+)(?:\[(\d+)\])?\(b\)',
            r'\.get\("n"\)\)&&\(b=([a-zA-Z0-9_$]+)\(b\)',
            r'([a-zA-Z0-9_$]+)=function\(a\)\{var b=a\.split\(""\)',
            r'function\s+([a-zA-Z0-9_$]+)\(a\)\{var b=a\.split\(""\)',
            r'([a-zA-Z0-9_$]+)=function\(a\)\{a=a\.split\(""\)',
        ]:
            m = re.search(pattern, code)
            if m:
                name = m.group(1)
                break
        if not name:
            return None
        body = self._extract_js_function_body(code, name)
        debug_log('n function', {'name': name, 'body_len': len(body)})
        if not body:
            return None

        def transform(value):
            arr = list(value)
            for part in body.split(';'):
                if 'reverse()' in part:
                    arr.reverse()
                m = re.search(r'\.slice\((\d+)\)', part)
                if m:
                    arr = arr[int(m.group(1)):]
                m = re.search(r'\.splice\(0,(\d+)\)', part)
                if m:
                    arr = arr[int(m.group(1)):]
            return ''.join(arr) or value
        return transform

    def _extract_js_function_body(self, code, name):
        starts = []
        for pattern in [
            r'function\s+' + re.escape(name) + r'\s*\([^)]*\)\s*\{',
            re.escape(name) + r'\s*=\s*function\s*\([^)]*\)\s*\{',
            r'var\s+' + re.escape(name) + r'\s*=\s*function\s*\([^)]*\)\s*\{',
        ]:
            m = re.search(pattern, code)
            if m:
                starts.append(m.end() - 1)
        if not starts:
            return ''
        start = starts[0]
        depth = 0
        in_str = None
        escape = False
        for i in range(start, len(code)):
            ch = code[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if in_str:
                if ch == in_str:
                    in_str = None
                continue
            if ch in ('"', "'", '`'):
                in_str = ch
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return code[start + 1:i]
        return ''

    def _extract_ytcfg(self, text):
        m = re.search(r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;', text, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except Exception:
            return None

    def _extract_initial_player_response(self, text):
        return self._extract_json_after(text, 'ytInitialPlayerResponse')

    def _extract_json_after(self, text, marker):
        pos = text.find(marker)
        if pos < 0:
            return None
        start = text.find('{', pos)
        if start < 0:
            return None
        depth = 0
        in_str = None
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if in_str:
                if ch == in_str:
                    in_str = None
                continue
            if ch == '"':
                in_str = ch
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        return None
        return None

    def _extract_player_url(self, text):
        for pattern in [
            r'"jsUrl":"([^"]+)"',
            r'"PLAYER_JS_URL":"([^"]+)"',
            r'(/s/player/[^"\\]+/base\.js)',
        ]:
            m = re.search(pattern, text)
            if m:
                return m.group(1).replace('\\/', '/')
        return ''

    @staticmethod
    def _search(pattern, text, default=None):
        m = re.search(pattern, text or '', re.S)
        return m.group(1) if m else default

    def trace(self, event, data=None):
        if self.config.get('trace', True):
            debug_log(event, data)

    def _extract_formats_from_responses(self, responses, player_url):
        formats = []
        sabr_formats = []
        seen_direct = set()
        seen_sabr = set()
        source_summary = []
        for response in responses:
            if not response:
                continue
            sd = response.get('streamingData') or {}
            raw_list = (sd.get('formats') or []) + (sd.get('adaptiveFormats') or [])
            client_name = response.get('_client_name')
            client_ua = response.get('_client_ua')
            client_info = response.get('_client_info') or {}
            server_abr_url = sd.get('serverAbrStreamingUrl')
            ustreamer_config = self._traverse(response, ('playerConfig', 'mediaCommonConfig', 'mediaUstreamerRequestConfig', 'videoPlaybackUstreamerConfig'))
            source_summary.append({
                'client': client_name,
                'formats': len(sd.get('formats') or []),
                'adaptive': len(sd.get('adaptiveFormats') or []),
                'has_sabr_url': bool(server_abr_url),
                'has_ustreamer': bool(ustreamer_config),
            })
            for raw0 in raw_list:
                raw = raw0.copy()
                raw['_client_name'] = client_name
                raw['_client_ua'] = client_ua
                direct_key = (client_name, raw.get('itag'), raw.get('url') or raw.get('signatureCipher') or raw.get('cipher') or raw.get('mimeType'))
                if direct_key not in seen_direct:
                    seen_direct.add(direct_key)
                    item = self._normalize_format(raw, player_url)
                    if item and item.get('url'):
                        formats.append(item)

                if server_abr_url and ustreamer_config:
                    sabr_key = (client_name, raw.get('itag'), raw.get('mimeType'), raw.get('xtags'))
                    if sabr_key not in seen_sabr:
                        seen_sabr.add(sabr_key)
                        sabr_item = self._normalize_sabr_format(raw, server_abr_url, ustreamer_config, client_name, client_ua, client_info)
                        if sabr_item:
                            sabr_formats.append(sabr_item)
        self.trace('formats extracted', {'sources': source_summary, 'direct': len(formats), 'sabr': len(sabr_formats)})
        return formats, sabr_formats

    def _normalize_sabr_format(self, fmt, server_abr_url, ustreamer_config, client_name, client_ua, client_info):
        mime = fmt.get('mimeType') or ''
        codecs = self._search(r'codecs="([^"]+)"', mime) or ''
        has_audio = mime.startswith('audio/') or any(x in codecs for x in ('mp4a', 'opus', 'vorbis'))
        has_video = mime.startswith('video/') or any(x in codecs for x in ('avc', 'vp9', 'vp09', 'av01', 'h264'))
        if has_audio and has_video:
            return None
        itag = fmt.get('itag')
        if not itag:
            return None
        headers = {}
        if client_ua:
            headers['User-Agent'] = client_ua
        po_token = self._get_po_token(client_name, 'gvs') if client_name else None
        return {
            'itag': itag,
            'url': server_abr_url.replace('.c.youtube.com/videoplayback', '.googlevideo.com/videoplayback'),
            'protocol': 'sabr',
            'mimeType': mime,
            'client': client_name,
            'ext': 'mp4' if 'mp4' in mime else 'webm' if 'webm' in mime else 'unknown',
            'width': fmt.get('width') or 0,
            'height': fmt.get('height') or 0,
            'fps': fmt.get('fps') or 0,
            'bitrate': fmt.get('bitrate') or fmt.get('averageBitrate') or 0,
            'contentLength': fmt.get('contentLength'),
            'codecs': codecs,
            'quality': fmt.get('qualityLabel') or fmt.get('quality'),
            'vcodec': codecs if has_video else 'none',
            'acodec': codecs if has_audio else 'none',
            'headers': headers,
            '_sabr_config': {
                'server_abr_streaming_url': server_abr_url,
                'video_playback_ustreamer_config': ustreamer_config,
                'client_name': client_name,
                'client_info': client_info,
                'po_token': po_token,
                'itag': itag,
                'xtags': fmt.get('xtags'),
                'last_modified': fmt.get('lastModified'),
                'target_duration_sec': fmt.get('targetDurationSec'),
            },
        }

    def _traverse(self, obj, path, default=None):
        cur = obj
        try:
            for key in path:
                if not isinstance(cur, dict):
                    return default
                cur = cur.get(key)
                if cur is None:
                    return default
            return cur
        except Exception:
            return default

    def sabr_first_chunk(self, video_item, audio_item=None, max_bytes=2 * 1024 * 1024, state_key=None):
        cfg = (video_item or {}).get('_sabr_config') or (audio_item or {}).get('_sabr_config') or {}
        if not cfg:
            raise Exception('missing sabr config')
        video_itag = video_item.get('itag') if video_item and video_item.get('vcodec') != 'none' else None
        audio_itag = audio_item.get('itag') if audio_item else None
        state_key = state_key or '%s:%s:%s' % (cfg.get('client_name'), video_itag or 0, audio_itag or 0)
        state = self.sabr_state.setdefault(state_key, {
            'playback_cookie': None, 'url': None, 'seen': [], 'request_count': 0,
            'initialized': {}, 'buffered': {}, 'player_time_ms': 0, 'init_media': {},
        })
        url = state.get('url') or cfg.get('server_abr_streaming_url') or video_item.get('url') or audio_item.get('url')
        headers = {
            'Content-Type': 'application/x-protobuf',
            'Accept': 'application/vnd.yt-ump',
            'Accept-Encoding': 'identity',
        }
        if video_item and video_item.get('headers'):
            headers.update(video_item.get('headers') or {})
        last_status = None
        media = bytearray()
        parts = []
        next_cookie = None
        redirect_url = None
        current_media_itag = None
        current_format_id = None
        current_header = None
        media_headers = []
        skipped_media_parts = 0
        duplicate_media_parts = 0
        max_parts = int(self.config.get('sabr_max_parts') or 512)
        seen = state.setdefault('seen', [])
        target_itag = video_itag or audio_itag
        for attempt in range(4):
            initialized_ids = list((state.get('initialized') or {}).values())
            buffered_ranges = []
            for br in (state.get('buffered') or {}).values():
                packed = build_buffered_range(
                    br.get('format_id'), br.get('start_ms') or 0, br.get('duration_ms') or 0,
                    br.get('start_seq'), br.get('end_seq'))
                if packed:
                    buffered_ranges.append(packed)
            payload = build_vpabr_request(
                cfg, video_itag=video_itag, audio_itag=audio_itag,
                start_time_ms=int(state.get('player_time_ms') or 0),
                playback_cookie=state.get('playback_cookie'),
                initialized_format_ids=initialized_ids, buffered_ranges=buffered_ranges)
            rn = int(state.get('request_count') or 0) + 1
            self.trace('sabr request', {
                'payload': len(payload), 'video_itag': video_itag, 'audio_itag': audio_itag, 'url_len': len(url or ''),
                'state_key': state_key, 'has_cookie': bool(state.get('playback_cookie')), 'rn': rn,
                'initialized': len(initialized_ids), 'buffered': len(buffered_ranges), 'player_time_ms': int(state.get('player_time_ms') or 0),
            })
            r = self.session.post(url, params={'rn': rn}, data=payload, headers=headers, stream=True, timeout=30)
            state['request_count'] = rn
            last_status = r.status_code
            self.trace('sabr http response', {'attempt': attempt + 1, 'rn': rn, 'status': r.status_code, 'content_type': r.headers.get('content-type'), 'content_length': r.headers.get('content-length'), 'encoding': r.headers.get('content-encoding'), 'host': urlparse(url or '').netloc})
            cur_redirect = None
            try:
                for part_id, part_data in iter_ump_parts(r.raw, max_parts=max_parts):
                    parts.append({'id': part_id, 'size': len(part_data)})
                    if part_id == UMP_MEDIA_HEADER:
                        current_media_itag = _pb_get_int(part_data, 3)
                        current_format_id = _sabr_header_format_id(part_data, current_media_itag)
                        is_init = _pb_get_int(part_data, 8)
                        seq = _pb_get_int(part_data, 9)
                        start_ms = _pb_get_int(part_data, 11) or 0
                        duration_ms = _pb_get_int(part_data, 12) or 0
                        if not start_ms and not duration_ms:
                            tr_start_ms, tr_duration_ms = _sabr_time_range_ms(part_data)
                            start_ms = tr_start_ms or start_ms
                            duration_ms = tr_duration_ms or duration_ms
                        if seq is not None and not duration_ms and not is_init:
                            # Some SABR MediaHeader omit timing. yt-dlp requires duration to progress;
                            # use targetDurationSec as conservative fallback so buffered_ranges/player_time advance.
                            duration_ms = int(float(cfg.get('target_duration_sec') or 5) * 1000)
                            start_ms = int(max(0, int(seq) - 1) * duration_ms)
                        current_header = {
                            'itag': current_media_itag, 'format_id': current_format_id, 'is_init': is_init,
                            'seq': seq, 'start_ms': start_ms, 'duration_ms': duration_ms,
                        }
                        media_headers.append({'itag': current_media_itag, 'size': len(part_data), 'is_init': is_init, 'seq': seq, 'start_ms': start_ms, 'duration_ms': duration_ms})
                        if current_format_id and is_init:
                            state.setdefault('initialized', {})[str(current_media_itag or current_format_id)] = current_format_id
                        continue
                    if part_id == UMP_MEDIA:
                        if target_itag and current_media_itag and int(current_media_itag) != int(target_itag):
                            skipped_media_parts += 1
                            continue
                        key = _sabr_media_key(part_data)
                        if key and key in seen:
                            duplicate_media_parts += 1
                            continue
                        if key:
                            seen.append(key)
                            if len(seen) > 512:
                                del seen[:-512]
                        media.extend(part_data)
                        if current_header and current_header.get('format_id'):
                            fmt_key = str(current_header.get('itag') or current_header.get('format_id'))
                            if current_header.get('is_init'):
                                state.setdefault('initialized', {})[fmt_key] = current_header.get('format_id')
                                # SABR 后续响应通常只给 media chunk，不再给 EBML/ftyp init。
                                # 本地代理每次都是独立 HTTP 响应，缓存 init 用于后续补头，避免播放器报不支持格式。
                                state.setdefault('init_media', {})[fmt_key] = bytes(part_data)
                            else:
                                seq = current_header.get('seq')
                                start_ms = int(current_header.get('start_ms') or 0)
                                duration_ms = int(current_header.get('duration_ms') or 0)
                                old = state.setdefault('buffered', {}).get(fmt_key)
                                if not old:
                                    state['buffered'][fmt_key] = {
                                        'format_id': current_header.get('format_id'), 'start_ms': start_ms, 'duration_ms': duration_ms,
                                        'start_seq': seq, 'end_seq': seq,
                                    }
                                else:
                                    end_ms = max(int(old.get('start_ms') or 0) + int(old.get('duration_ms') or 0), start_ms + duration_ms)
                                    old['start_ms'] = min(int(old.get('start_ms') or 0), start_ms)
                                    old['duration_ms'] = max(0, end_ms - int(old.get('start_ms') or 0))
                                    if seq is not None:
                                        old['start_seq'] = seq if old.get('start_seq') is None else min(old.get('start_seq'), seq)
                                        old['end_seq'] = seq if old.get('end_seq') is None else max(old.get('end_seq'), seq)
                                if start_ms or duration_ms:
                                    state['player_time_ms'] = max(int(state.get('player_time_ms') or 0), start_ms + duration_ms)
                        if len(media) >= max_bytes:
                            break
                    elif part_id == UMP_NEXT_REQUEST_POLICY:
                        next_cookie = _pb_get_bytes(part_data, 7)
                        if next_cookie:
                            state['playback_cookie'] = next_cookie
                    elif part_id == UMP_SABR_REDIRECT:
                        cur_redirect = _pb_get_str(part_data, 1)
                        redirect_url = cur_redirect
                        if cur_redirect:
                            state['url'] = cur_redirect
                        self.trace('sabr redirect part', {'url_len': len(cur_redirect or ''), 'host': urlparse(cur_redirect or '').netloc})
                    elif part_id == UMP_SABR_ERROR:
                        err_type = _pb_get_str(part_data, 1)
                        action = _pb_get_int(part_data, 2)
                        err_msg = _pb_get_bytes(part_data, 3) or b''
                        err_status = _pb_get_int(err_msg, 1)
                        err_inner_type = _pb_get_int(err_msg, 4)
                        self.trace('sabr error part', {'type': err_type, 'action': action, 'status_code': err_status, 'inner_type': err_inner_type, 'size': len(part_data)})
                    elif part_id in (UMP_RELOAD_PLAYER_RESPONSE, UMP_STREAM_PROTECTION_STATUS):
                        self.trace('sabr control part', {'id': part_id, 'size': len(part_data)})
            finally:
                try:
                    r.close()
                except Exception:
                    pass
            if len(media) >= max_bytes:
                break
            if cur_redirect:
                url = cur_redirect
                continue
            if media:
                break
            break
        self.trace('sabr response', {
            'status': last_status, 'parts': parts[:40], 'media_len': len(media),
            'has_cookie': bool(state.get('playback_cookie') or next_cookie), 'redirect': bool(redirect_url or state.get('url')),
            'media_headers': media_headers[:12], 'skipped_media_parts': skipped_media_parts,
            'duplicate_media_parts': duplicate_media_parts, 'state_seen': len(seen),
            'initialized': len(state.get('initialized') or {}), 'buffered': list((state.get('buffered') or {}).values())[:4],
            'player_time_ms': int(state.get('player_time_ms') or 0),
        })
        return bytes(media), {'status': last_status, 'parts': parts, 'next_cookie': state.get('playback_cookie') or next_cookie, 'redirect_url': redirect_url or state.get('url'), 'media_headers': media_headers, 'skipped_media_parts': skipped_media_parts, 'duplicate_media_parts': duplicate_media_parts}

    def sabr_get_segment(self, video_item, audio_item, track, segment, state_key):
        """Fetch a complete SABR init/media segment for the local DASH bridge.

        Mirrors yt-dlp's SabrStream/SabrFD contract: MEDIA_HEADER opens a segment,
        MEDIA parts are routed by their leading header_id varint, and MEDIA_END
        atomically publishes the completed segment.
        """
        cfg = (video_item or {}).get('_sabr_config') or (audio_item or {}).get('_sabr_config') or {}
        if not cfg:
            raise Exception('missing sabr config')
        video_itag = int((video_item or {}).get('itag') or 0) or None
        audio_itag = int((audio_item or {}).get('itag') or 0) or None
        state = self.sabr_state.setdefault(state_key, {
            'playback_cookie': None, 'url': None, 'request_count': 0,
            'initialized': {}, 'buffered': {}, 'player_time_ms': 0,
            'partial': {}, 'init_segments': {}, 'segments': {},
            'segment_meta': {}, 'segment_order': {},
            'lock': threading.RLock(), 'last_status': None,
        })
        # Upgrade a state created by an older implementation without losing cookies.
        state.setdefault('partial', {})
        state.setdefault('init_segments', {})
        state.setdefault('segments', {})
        state.setdefault('segment_meta', {})
        state.setdefault('segment_order', {})
        state.setdefault('initialized', {})
        state.setdefault('buffered', {})
        state.setdefault('lock', threading.RLock())
        target_itag = video_itag if track == 'video' else audio_itag
        if not target_itag:
            return None, {'error': 'track not selected', 'track': track}
        want_init = str(segment) == 'init'
        try:
            want_seq = None if want_init else int(segment)
        except Exception:
            return None, {'error': 'invalid segment', 'segment': segment}
        # DASH $Number$ 是本地桥的编号，不等于 YouTube SABR 原生 sequence_number。
        # 必须先换算成时间，再按 MediaHeader.start_ms/duration_ms 查找原生段。
        track_cfg = ((video_item if track == 'video' else audio_item) or {}).get('_sabr_config') or {}
        dash_seg_ms = int(float((track_cfg.get('target_duration_sec') or (6 if track == 'video' else 10)) * 1000))
        if track == 'audio' and dash_seg_ms < 8000:
            dash_seg_ms = 10000
        if dash_seg_ms <= 0:
            dash_seg_ms = 6000 if track == 'video' else 10000
        target_ms = None if want_init else max(0, (want_seq - 1) * dash_seg_ms)
        max_pumps = int(self.config.get('sabr_segment_fetch_requests') or 10)

        with state['lock']:
            if want_init:
                found = state['init_segments'].get(target_itag)
                if found is not None:
                    return found, {'status': state.get('last_status'), 'itag': target_itag,
                                    'segment': segment, 'request_count': state.get('request_count')}

            seeked = False
            transport_retries = 0
            for _ in range(max_pumps):
                if want_init:
                    found, native_seq, native_meta = state['init_segments'].get(target_itag), None, None
                else:
                    found, native_seq, native_meta = self._sabr_find_segment_by_time(
                        state, target_itag, target_ms, dash_seg_ms)
                if found is not None:
                    return found, {
                        'status': state.get('last_status'), 'itag': target_itag,
                        'segment': segment, 'request_count': state.get('request_count'),
                        'seeked': seeked, 'target_ms': target_ms,
                        'native_seq': native_seq, 'native_meta': native_meta,
                    }
                if not want_init and not seeked and self._sabr_should_seek_time(
                        state, target_itag, target_ms, dash_seg_ms):
                    self._sabr_seek(state, target_ms)
                    seeked = True
                    self.trace('sabr seek', {
                        'itag': target_itag, 'dash_number': want_seq, 'seek_ms': target_ms,
                        'cached_time_range': self._sabr_cached_time_range(state, target_itag),
                    })
                try:
                    self._sabr_pump_once(state, cfg, video_item, audio_item)
                    transport_retries = 0
                except Exception as e:
                    if not self._sabr_is_retryable_transport_error(e) or transport_retries >= 2:
                        raise
                    transport_retries += 1
                    state['partial'] = {}
                    self.trace('sabr transport retry', {
                        'attempt': transport_retries, 'error': repr(e),
                        'track': track, 'dash_number': want_seq,
                    })
            return None, {
                'error': 'segment not produced by SABR server', 'itag': target_itag,
                'segment': segment, 'target_ms': target_ms,
                'request_count': state.get('request_count'),
                'native_available': sorted((state['segments'].get(target_itag) or {}).keys())[-12:],
                'cached_time_range': self._sabr_cached_time_range(state, target_itag),
                'seeked': seeked,
            }

    @staticmethod
    def _sabr_find_segment_by_time(state, target_itag, target_ms, dash_seg_ms):
        media = state.get('segments', {}).get(target_itag) or {}
        metas = state.get('segment_meta', {}).get(target_itag) or {}
        candidates = []
        for native_seq, meta in metas.items():
            start = int(meta.get('start_ms') or 0)
            duration = int(meta.get('duration_ms') or 0)
            end = start + max(1, duration)
            if start <= target_ms < end:
                candidates.append((start, native_seq, meta))
        if not candidates:
            # 容忍 MPD 固定时长与原生变长段边界的小偏差，但绝不按编号硬匹配。
            for native_seq, meta in metas.items():
                start = int(meta.get('start_ms') or 0)
                if abs(start - target_ms) <= min(2000, max(500, dash_seg_ms // 3)):
                    candidates.append((start, native_seq, meta))
        if not candidates:
            return None, None, None
        _, native_seq, meta = min(candidates, key=lambda x: abs(x[0] - target_ms))
        return media.get(native_seq), native_seq, meta

    @staticmethod
    def _sabr_cached_time_range(state, target_itag):
        metas = (state.get('segment_meta') or {}).get(target_itag) or {}
        if not metas:
            return None
        starts = [int(x.get('start_ms') or 0) for x in metas.values()]
        ends = [int(x.get('start_ms') or 0) + int(x.get('duration_ms') or 0) for x in metas.values()]
        return [min(starts), max(ends)]

    @classmethod
    def _sabr_should_seek_time(cls, state, target_itag, target_ms, dash_seg_ms):
        cached = cls._sabr_cached_time_range(state, target_itag)
        if not cached:
            current = int(state.get('player_time_ms') or 0)
            return current > target_ms + dash_seg_ms or target_ms > current + (2 * dash_seg_ms)
        return target_ms < cached[0] or target_ms > cached[1] + dash_seg_ms

    @staticmethod
    def _sabr_is_retryable_transport_error(error):
        text = repr(error)
        return any(x in text for x in (
            'IncompleteRead', 'ProtocolError', 'ChunkedEncodingError',
            'RemoteDisconnected', 'Connection reset', 'Read timed out'))


    @staticmethod
    def _sabr_seek(state, seek_ms):
        # 重置到目标时间点：清空 buffered_ranges 与 initialized，让服务器从 seek_ms 重新发段。
        # 已下载分段保留在 state['segments']，seek 只影响“下一次请求从哪开始”。
        state['player_time_ms'] = int(seek_ms)
        state['buffered'] = {}
        state['initialized'] = {}
        state['partial'] = {}

    def _sabr_pump_once(self, state, cfg, video_item, audio_item):
        video_itag = int((video_item or {}).get('itag') or 0) or None
        audio_itag = int((audio_item or {}).get('itag') or 0) or None
        initialized_ids = list((state.get('initialized') or {}).values())
        buffered_ranges = []
        for br in (state.get('buffered') or {}).values():
            packed = build_buffered_range(
                br.get('format_id'), br.get('start_ms') or 0, br.get('duration_ms') or 0,
                br.get('start_seq'), br.get('end_seq'))
            if packed:
                buffered_ranges.append(packed)
        payload = build_vpabr_request(
            cfg, video_itag=video_itag, audio_itag=audio_itag,
            start_time_ms=int(state.get('player_time_ms') or 0),
            playback_cookie=state.get('playback_cookie'),
            initialized_format_ids=initialized_ids, buffered_ranges=buffered_ranges)
        url = state.get('url') or cfg.get('server_abr_streaming_url') or (video_item or {}).get('url')
        headers = {
            'Content-Type': 'application/x-protobuf', 'Accept': 'application/vnd.yt-ump',
            'Accept-Encoding': 'identity',
        }
        headers.update((video_item or {}).get('headers') or (audio_item or {}).get('headers') or {})
        target_itags = set(x for x in (video_itag, audio_itag) if x)

        for redirect_attempt in range(4):
            rn = int(state.get('request_count') or 0) + 1
            self.trace('sabr segment request', {
                'rn': rn, 'video_itag': video_itag, 'audio_itag': audio_itag,
                'player_time_ms': int(state.get('player_time_ms') or 0),
                'initialized': len(initialized_ids), 'buffered': len(buffered_ranges),
                'host': urlparse(url or '').netloc,
            })
            response = self.session.post(
                url, params={'rn': rn}, data=payload, headers=headers, stream=True, timeout=30)
            state['request_count'] = rn
            state['last_status'] = response.status_code
            redirect_url = None
            completed = []
            part_count = 0
            try:
                if response.status_code != 200:
                    try:
                        error_body = (response.raw.read(512) or b'').decode('utf-8', 'replace')
                    except Exception:
                        error_body = ''
                    self.trace('sabr http error', {
                        'status': response.status_code,
                        'client': cfg.get('client_name'),
                        'host': urlparse(url or '').netloc,
                        'content_type': response.headers.get('content-type'),
                        'body': error_body[:300],
                    })
                    raise Exception(f'SABR HTTP {response.status_code} client={cfg.get("client_name")}')
                for part_id, part_data in iter_ump_parts(
                        response.raw, max_parts=int(self.config.get('sabr_max_parts') or 4096)):
                    part_count += 1
                    if part_id == UMP_MEDIA_HEADER:
                        header_id = _pb_get_int(part_data, 1)
                        itag = _pb_get_int(part_data, 3)
                        if header_id is None:
                            continue
                        format_id = _sabr_header_format_id(part_data, itag)
                        is_init = bool(_pb_get_int(part_data, 8))
                        seq = _pb_get_int(part_data, 9)
                        start_ms = _pb_get_int(part_data, 11) or 0
                        duration_ms = _pb_get_int(part_data, 12) or 0
                        if not start_ms and not duration_ms:
                            start_ms, duration_ms = _sabr_time_range_ms(part_data)
                        state['partial'][header_id] = {
                            'header_id': header_id, 'itag': itag, 'format_id': format_id,
                            'is_init': is_init, 'seq': seq, 'start_ms': start_ms,
                            'duration_ms': duration_ms, 'expected': _pb_get_int(part_data, 14),
                            'data': bytearray(),
                        }
                    elif part_id == UMP_MEDIA:
                        header_id, data_pos = _read_ump_varint_bytes(part_data)
                        partial = state['partial'].get(header_id)
                        if partial and partial.get('itag') in target_itags:
                            # The leading UMP varint is routing metadata, never media bytes.
                            partial['data'].extend(part_data[data_pos:])
                    elif part_id == UMP_MEDIA_END:
                        header_id, _ = _read_ump_varint_bytes(part_data)
                        partial = state['partial'].pop(header_id, None)
                        if not partial or partial.get('itag') not in target_itags:
                            continue
                        media = bytes(partial.get('data') or b'')
                        expected = partial.get('expected')
                        if expected is not None and int(expected) != len(media):
                            self.trace('sabr segment size mismatch', {
                                'header_id': header_id, 'itag': partial.get('itag'),
                                'seq': partial.get('seq'), 'expected': expected, 'actual': len(media),
                            })
                            continue
                        itag = partial.get('itag')
                        if partial.get('is_init'):
                            state['init_segments'][itag] = media
                            if partial.get('format_id'):
                                state['initialized'][str(itag)] = partial.get('format_id')
                        elif partial.get('seq') is not None:
                            seq = int(partial.get('seq'))
                            state['segments'].setdefault(itag, {})[seq] = media
                            state['segment_meta'].setdefault(itag, {})[seq] = {
                                'start_ms': int(partial.get('start_ms') or 0),
                                'duration_ms': int(partial.get('duration_ms') or 0),
                                'size': len(media),
                            }
                            order = state['segment_order'].setdefault(itag, [])
                            if seq in order:
                                order.remove(seq)
                            order.append(seq)
                            self._sabr_commit_buffered(state, partial)
                            self._sabr_trim_cache(
                                state, itag,
                                int(self.config.get(
                                    'sabr_video_cache_bytes' if itag == video_itag else 'sabr_audio_cache_bytes')
                                    or (192 * 1024 * 1024 if itag == video_itag else 16 * 1024 * 1024)))
                        completed.append({
                            'itag': itag, 'seq': partial.get('seq'),
                            'init': partial.get('is_init'), 'size': len(media),
                        })
                    elif part_id == UMP_NEXT_REQUEST_POLICY:
                        cookie = _pb_get_bytes(part_data, 7)
                        if cookie:
                            state['playback_cookie'] = cookie
                    elif part_id == UMP_SABR_REDIRECT:
                        redirect_url = _pb_get_str(part_data, 1)
                        if redirect_url:
                            state['url'] = redirect_url
                    elif part_id == UMP_SABR_ERROR:
                        self.trace('sabr error part', {
                            'type': _pb_get_str(part_data, 1), 'action': _pb_get_int(part_data, 2),
                        })
            finally:
                response.close()
            self.trace('sabr segment response', {
                'rn': rn, 'status': state.get('last_status'), 'parts': part_count,
                'completed': completed[:16], 'redirect': bool(redirect_url),
                'player_time_ms': state.get('player_time_ms'),
            })
            if redirect_url and not completed:
                url = redirect_url
                continue
            return

    @staticmethod
    def _sabr_trim_cache(state, itag, max_bytes):
        """Evict oldest completed segments by insertion order and total bytes."""
        media = state.get('segments', {}).get(itag) or {}
        metas = state.get('segment_meta', {}).get(itag) or {}
        order = state.get('segment_order', {}).get(itag) or []
        total = sum(len(value) for value in media.values())
        # Always retain at least two segments so immediate player retries can hit cache.
        while total > max_bytes and len(order) > 2:
            old_seq = order.pop(0)
            old_media = media.pop(old_seq, None)
            metas.pop(old_seq, None)
            if old_media is not None:
                total -= len(old_media)
        state.setdefault('segment_order', {})[itag] = order

    @staticmethod
    def _sabr_commit_buffered(state, segment):
        format_id = segment.get('format_id')
        if not format_id:
            return
        seq = segment.get('seq')
        start_ms = int(segment.get('start_ms') or 0)
        duration_ms = int(segment.get('duration_ms') or 0)
        key = str(segment.get('itag') or format_id)
        old = state['buffered'].get(key)
        if not old:
            old = state['buffered'][key] = {
                'format_id': format_id, 'start_ms': start_ms, 'duration_ms': duration_ms,
                'start_seq': seq, 'end_seq': seq,
            }
        else:
            old_end = int(old.get('start_ms') or 0) + int(old.get('duration_ms') or 0)
            end_ms = max(old_end, start_ms + duration_ms)
            old['start_ms'] = min(int(old.get('start_ms') or 0), start_ms)
            old['duration_ms'] = max(0, end_ms - int(old.get('start_ms') or 0))
            if seq is not None:
                old['start_seq'] = seq if old.get('start_seq') is None else min(old['start_seq'], seq)
                old['end_seq'] = seq if old.get('end_seq') is None else max(old['end_seq'], seq)
        state['player_time_ms'] = max(int(state.get('player_time_ms') or 0), start_ms + duration_ms)

class Spider(Spider):
    def getName(self):
        return 'YouTube视频'

    def init(self, extend):
        try:
            self.extendDict = json.loads(extend) if extend else {}
        except Exception:
            self.extendDict = {}
        self.session = requests.Session()
        # 未显式指定代理时允许 requests 继续使用系统/环境变量代理。
        self.session.trust_env = True

        # 代理三级回退：ext 显式代理 > 内置本机节点 > 系统/全局代理。
        self.proxy_str = None
        proxy_val = self.extendDict.get('proxy')
        if proxy_val:
            if isinstance(proxy_val, str):
                proxy_url = proxy_val.strip()
                if proxy_url and not proxy_url.startswith(('http://', 'https://')):
                    proxy_url = 'http://' + proxy_url
                if proxy_url:
                    self.session.proxies = {'http': proxy_url, 'https': proxy_url}
                    self.proxy_str = proxy_url.replace('http://', '').replace('https://', '')
                    debug_log('使用 ext 传入代理', {'proxy': proxy_url})
                else:
                    self._auto_detect_proxy()
            elif isinstance(proxy_val, dict):
                proxies = {}
                for scheme, value in proxy_val.items():
                    if scheme not in ('http', 'https') or not value:
                        continue
                    proxy_url = str(value).strip()
                    if not proxy_url.startswith(('http://', 'https://')):
                        proxy_url = 'http://' + proxy_url
                    proxies[scheme] = proxy_url
                if proxies:
                    self.session.proxies = proxies
                    selected_proxy = proxies.get('https') or proxies.get('http') or ''
                    self.proxy_str = selected_proxy.replace('http://', '').replace('https://', '')
                    debug_log('使用 ext 传入的字典代理', proxies)
                else:
                    self._auto_detect_proxy()
            else:
                self._auto_detect_proxy()
        else:
            self._auto_detect_proxy()
        self.header = {

            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.youtube.com/'
        }
        self.session.headers.update(self.header)
        self.yt = YouTubeLite(self.session, self.header, self.extendDict)
        self.config = {}
        self.search_page_cache = {}
        self.sabr_switch_lock = threading.RLock()


    def _auto_detect_proxy(self):
        """依次探测内置本机代理；均不可用时回退到系统/环境代理。"""
        proxy_list = [
            'http://127.0.0.1:2080',
            'http://127.0.0.1:7890',
            'http://127.0.0.1:10809',
            'http://127.0.0.1:10172',
            'http://127.0.0.1:20172',
            'http://127.0.0.1:7891',
            'http://127.0.0.1:10808',
            'http://127.0.0.1:1087',
            'http://127.0.0.1:3128',
            'http://127.0.0.1:1080',
            'http://127.0.0.1:8080',
            'http://127.0.0.1:9090',
        ]
        for proxy_url in proxy_list:
            response = None
            try:
                test_proxies = {'http': proxy_url, 'https': proxy_url}
                response = requests.get(
                    'https://www.youtube.com', proxies=test_proxies, timeout=2)
                if response.status_code < 400:
                    self.session.proxies = test_proxies
                    self.proxy_str = proxy_url.replace('http://', '').replace('https://', '')
                    debug_log('内置代理探测成功，使用内置', {'proxy': proxy_url})
                    return
            except Exception:
                continue
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass

        # trust_env 保持开启；清空会话代理后由 requests 自动读取系统环境代理。
        self.session.proxies = {}
        self.proxy_str = ''
        debug_log('所有内置代理均不可用，清空设置，回退使用系统/全局代理')

    def homeContent(self, filter):
        result = {'class': YOUTUBE_CLASSES}
        if filter:
            result['filters'] = CATEGORY_FILTERS
        return result

    def homeVideoContent(self):
        return {'list': []}

    def categoryContent(self, cid, page, filter, ext):
        page = int(page)
        filters = ext if isinstance(ext, dict) else {}
        query = self._build_category_keyword(cid, filters)
        videos, has_more = self._search_youtube_page(query, page)
        return {'list': videos, 'page': page, 'pagecount': page + 1 if has_more else page, 'limit': len(videos), 'total': len(videos)}

    def searchContent(self, key, quick, pg=1):
        page = int(pg)
        videos, has_more = self._search_youtube_page(key, page)
        return {'list': videos, 'page': page, 'pagecount': page + 1 if has_more else page, 'limit': len(videos), 'total': len(videos)}

    def detailContent(self, did):
        video_id = did[0]
        title = self._get_video_title(video_id)
        safe_title = self._safe_title(title)
        play_sources = []
        play_urls = []
        try:
            data = self.yt.extract(video_id)
            formats = data.get('formats') or []
            quality_groups = [
                ('best', {'SDR': 'best', 'HDR': 'hdr'}),
                ('8k', {'SDR': '8k', 'HDR': '8k_hdr'}),
            ]
            seen_sources = set()
            for select_quality, quality_map in quality_groups:
                tracks = self.yt.choose_video_tracks(formats, select_quality)
                for track in tracks:
                    height = int(track.get('height') or 0)
                    kind = track.get('track_name') or ('HDR' if track.get('is_hdr') else 'SDR')
                    if select_quality == '8k' and height < 4320:
                        continue
                    name = f'{height}p {kind}' if height else kind
                    # 仅替换 2160p 线路展示名称，quality 与轨道选择逻辑保持不变。
                    name = {
                        (2160, 'SDR'): 'VCE SDR4K',
                        (2160, 'HDR'): 'VCE HDR4K',
                    }.get((height, kind), name)
                    if name in seen_sources:
                        continue
                    seen_sources.add(name)
                    quality = quality_map.get(kind, select_quality)
                    play_sources.append(name)
                    play_urls.append(f'{safe_title} {name}${video_id}@{quality}')
            if data.get('sabr_formats'):
                play_sources.append('SABR实验')
                play_urls.append(f'{safe_title} SABR${video_id}@sabr')
            debug_log('detail dynamic sources', {
                'video_id': video_id, 'sources': play_sources,
                'sabr_formats': len(data.get('sabr_formats') or []),
            })
        except Exception as e:
            debug_log('detail dynamic sources error', {'video_id': video_id, 'error': repr(e)})
        if not play_sources:
            play_sources = ['SDR', 'HDR']
            play_urls = [
                f'{safe_title} SDR${video_id}@best',
                f'{safe_title} HDR${video_id}@hdr',
            ]
        vod = {
            'vod_id': video_id,
            'vod_name': title,
            'vod_pic': f'http://127.0.0.1:9978/proxy?do=py&type=image&vid={video_id}&quality=hqdefault',
            'vod_play_from': '$$$'.join(play_sources),
            'vod_play_url': '$$$'.join(play_urls)
        }
        return {'list': [vod]}

    def _build_direct_play_url(self, media_url, headers, ext):
        header_query = urlencode({k: v for k, v in (headers or {}).items() if v})
        return f'{media_url}|{header_query}' if header_query else media_url

    def playerContent(self, flag, pid, vipFlags):
        raw_pid = pid.split('$')[-1]
        if '@' in raw_pid:
            video_id, quality = raw_pid.rsplit('@', 1)
        else:
            video_id, quality = raw_pid, '1080p'
        if quality not in ('best', 'hdr', '8k', '8k_hdr', '4k', '2k', '1080p', 'sabr'):
            quality = 'best'
        debug_log('playerContent', {'flag': flag, 'pid': pid, 'video_id': video_id, 'quality': quality})
        try:
            data = self.yt.extract(video_id)
            if quality == 'sabr':
                sabr_data = self._new_sabr_play_data(video_id, data, 'best')
                if not sabr_data:
                    raise Exception('没有可用的独立 SABR 客户端音视频组')
                video = sabr_data['video_item']
                audio = sabr_data['audio_item']
                debug_log('return true sabr mpd', {
                    'video': video.get('itag'), 'audio': audio.get('itag'),
                    'client': video.get('client'), 'height': video.get('height'),
                    'candidate_count': len(sabr_data.get('sabr_candidates') or []),
                })
                return {
                    'parse': 0, 'jx': 0,
                    'url': f'http://127.0.0.1:9978/proxy?do=py&type=sabr_mpd&vid={video_id}',
                    'format': 'application/dash+xml',
                }
            select_quality = quality if quality in ('8k', '8k_hdr', '4k', '2k', '1080p') else 'best'
            all_tracks = self.yt.choose_video_tracks(data['formats'], select_quality)
            wanted_name = 'HDR' if quality in ('hdr', '8k_hdr') else 'SDR'
            video_tracks = [x for x in all_tracks if x.get('track_name') == wanted_name]
            if not video_tracks and all_tracks and quality not in ('8k', '8k_hdr'):
                video_tracks = [all_tracks[0]]
            if video_tracks:
                audio, audio_candidates = self._choose_direct_audio(data['formats'])
                debug_log('selected track', {'requested': wanted_name, 'track': {'name': video_tracks[0].get('track_name'), 'itag': video_tracks[0].get('itag'), 'height': video_tracks[0].get('height'), 'mime': video_tracks[0].get('mimeType')}, 'audio': audio.get('itag') if audio else None})
                if audio:
                    cache_key = f'yt_{video_id}_{quality}'
                    self.setCache(cache_key, {
                        'video_tracks': video_tracks,
                        'video_url': video_tracks[0]['url'],
                        'audio_url': audio['url'],
                        'video_item': video_tracks[0],
                        'audio_item': audio,
                        'audio_candidates': audio_candidates,
                        'failed_audio_keys': [],
                        'duration': data.get('duration') or 0,
                        'expires': time.time() + 21600,
                    })
                    return {'parse': 0, 'jx': 0, 'url': f'http://127.0.0.1:9978/proxy?do=py&type=mpd&vid={video_id}&quality={quality}', 'format': 'application/dash+xml'}
                playable = video_tracks[0]
                headers = self.header.copy()
                headers.update(playable.get('headers') or {})
                self.setCache(f'yt_single_{video_id}', {
                    'url': playable['url'],
                    'headers': headers,
                    'expires': time.time() + 21600,
                })
                debug_log('return proxied single stream', {
                    'video_id': video_id, 'itag': playable.get('itag'),
                    'client': playable.get('client'),
                })
                return {
                    'parse': 0, 'jx': 0,
                    'url': f'http://127.0.0.1:9978/proxy?do=py&type=single&vid={video_id}',
                    'header': self.header,
                }
            raise Exception(f'没有可直接播放的 {quality} 视频流格式')
        except Exception as e:
            debug_log('playerContent error', repr(e))
            print(f'[YouTubeLite] 解析失败: {e}')
            res = {'parse': 1, 'url': f'https://www.youtube.com/embed/{video_id}?autoplay=1', 'header': json.dumps(self.header)}
            if self.proxy_str:
                res['proxy'] = self.proxy_str
            return res

    def localProxy(self, params):
        if params.get('do') != 'py':
            return None
        if params.get('type') == 'mpd':
            return self._proxy_mpd(params)
        if params.get('type') == 'media':
            return self._proxy_media(params)
        if params.get('type') == 'single':
            return self._proxy_single(params)
        if params.get('type') == 'image':
            return self._proxy_image(params)
        if params.get('type') == 'sabr_mpd':
            return self._proxy_sabr_mpd(params)
        if params.get('type') == 'sabr':
            return self._proxy_sabr(params)
        return None

    def _proxy_image(self, params):
        """通过主 Session 获取缩略图，继承与 API/播放流相同的代理设置。"""
        vid = str(params.get('vid') or '').strip()
        if not re.fullmatch(r'[0-9A-Za-z_-]{11}', vid):
            return [400, 'text/plain', '无效的 video id']

        requested = str(params.get('quality') or 'hqdefault').strip().lower()
        allowed = ('maxresdefault', 'sddefault', 'hqdefault', 'mqdefault', 'default')
        if requested not in allowed:
            requested = 'hqdefault'
        qualities = []
        for quality in (requested, 'hqdefault', 'mqdefault', 'default'):
            if quality not in qualities:
                qualities.append(quality)

        headers = self.header.copy()
        headers.update({
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Referer': f'https://www.youtube.com/watch?v={vid}',
        })
        last_status = None
        for quality in qualities:
            image_url = f'https://i.ytimg.com/vi/{vid}/{quality}.jpg'
            response = None
            try:
                response = self.session.get(
                    image_url, headers=headers, timeout=10, allow_redirects=True)
                last_status = response.status_code
                content_type = response.headers.get('content-type', '').split(';', 1)[0]
                if response.status_code == 200 and response.content and content_type.startswith('image/'):
                    body = bytes(response.content)
                    debug_log('proxy image response', {
                        'vid': vid, 'quality': quality, 'status': response.status_code,
                        'content_type': content_type, 'content_length': len(body),
                    })
                    return [200, content_type or 'image/jpeg', body, {
                        'Cache-Control': 'public, max-age=86400',
                        'Content-Length': str(len(body)),
                    }]
                debug_log('proxy image candidate failed', {
                    'vid': vid, 'quality': quality, 'status': response.status_code,
                    'content_type': content_type,
                })
            except Exception as e:
                debug_log('proxy image request error', {
                    'vid': vid, 'quality': quality, 'error': repr(e),
                })
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass
        return [404, 'text/plain', f'图片不存在或代理请求失败 ({last_status})']

    @staticmethod
    def _direct_audio_key(item):
        return (
            str((item or {}).get('client') or ''),
            int((item or {}).get('itag') or 0),
            str((item or {}).get('codecs') or '').lower(),
        )

    @staticmethod
    def _direct_audio_signature(item):
        return (
            int((item or {}).get('itag') or 0),
            ((item or {}).get('mimeType') or '').split(';')[0].lower(),
            str((item or {}).get('codecs') or '').lower(),
        )

    def _direct_audio_candidates(self, formats, failed_keys=None, required_signature=None):
        failed = set(tuple(x) for x in (failed_keys or []))
        audios = [
            x for x in (formats or [])
            if x.get('protocol') != 'sabr' and x.get('url')
            and x.get('acodec') != 'none' and x.get('vcodec') == 'none'
            and self._direct_audio_key(x) not in failed
        ]
        risky_markers = ('ec-3', 'ec3', 'eac3', 'ac-3', 'ac3', 'dts', 'truehd')
        safe = [x for x in audios if not any(m in ((x.get('codecs') or '') + ' ' + (x.get('mimeType') or '')).lower() for m in risky_markers)]
        # EC-3/AC-3 等只在没有任何常规音轨时兜底，避免高码率覆盖 AAC。
        audios = safe or audios
        if required_signature is not None:
            audios = [x for x in audios if self._direct_audio_signature(x) == tuple(required_signature)]
        client_order = {'ANDROID_VR': 6, 'IOS': 5, 'MWEB': 4, 'ANDROID': 3, 'WEB_INITIAL': 2, 'WEB': 1}

        def codec_rank(item):
            text = ((item.get('codecs') or '') + ' ' + (item.get('mimeType') or '')).lower()
            if 'mp4a' in text or 'aac' in text:
                return 5
            if 'opus' in text:
                return 4
            if 'vorbis' in text:
                return 3
            if 'mp3' in text:
                return 2
            return 1

        audios.sort(key=lambda x: (
            codec_rank(x),
            client_order.get(str(x.get('client') or '').upper(), 0),
            1 if int(x.get('itag') or 0) == 140 else 0,
            int(x.get('bitrate') or 0),
        ), reverse=True)
        # 同一客户端/itag/编码只保留一条；URL 变化由强制刷新负责。
        result = []
        seen = set()
        for item in audios:
            key = self._direct_audio_key(item)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        debug_log('direct audio candidates', {
            'failed': [list(x) for x in failed],
            'items': [{
                'client': x.get('client'), 'itag': x.get('itag'),
                'codecs': x.get('codecs'), 'bitrate': x.get('bitrate'),
            } for x in result[:10]],
        })
        return result

    def _choose_direct_audio(self, formats, failed_keys=None, required_signature=None):
        candidates = self._direct_audio_candidates(formats, failed_keys, required_signature)
        selected = candidates[0] if candidates else None
        debug_log('direct audio selected', {
            'client': selected.get('client') if selected else None,
            'itag': selected.get('itag') if selected else None,
            'codecs': selected.get('codecs') if selected else None,
            'candidate_count': len(candidates),
        })
        return selected, candidates

    def _next_cached_direct_audio(self, data, failed_item):
        failed_keys = [tuple(x) for x in (data.get('failed_audio_keys') or [])]
        failed_key = self._direct_audio_key(failed_item)
        if failed_key not in failed_keys:
            failed_keys.append(failed_key)
        primary_signature = self._direct_audio_signature(data.get('audio_item') or failed_item)
        candidates = data.get('audio_candidates') or []
        # MPD 已下发，运行时只切换相同 itag/容器/编码，保证 SegmentBase 兼容。
        remaining = [
            x for x in candidates
            if self._direct_audio_key(x) not in failed_keys
            and self._direct_audio_signature(x) == primary_signature
        ]
        data['failed_audio_keys'] = [list(x) for x in failed_keys]
        if not remaining:
            return None
        selected = remaining[0]
        data['audio_item'] = selected
        data['audio_url'] = selected.get('url')
        debug_log('direct audio cache failover', {
            'from': list(failed_key), 'to': list(self._direct_audio_key(selected)),
            'remaining_same_format': len(remaining),
        })
        return selected

    def _rebuild_play_cache(self, vid, quality, force_refresh=False, failed_audio_keys=None, required_audio_signature=None):
        # 历史记录可能只保留本地 MPD 地址；缓存丢失时重新解析并回填。
        # failed_audio_keys 用于避免 403 后再次选回同一客户端/itag/编码。
        try:
            data = self.yt.extract(vid, force_refresh=force_refresh)
            select_quality = quality if quality in ('8k', '8k_hdr', '4k', '2k', '1080p') else 'best'
            all_tracks = self.yt.choose_video_tracks(data['formats'], select_quality)
            wanted_name = 'HDR' if quality in ('hdr', '8k_hdr') else 'SDR'
            video_tracks = [x for x in all_tracks if x.get('track_name') == wanted_name]
            if not video_tracks and all_tracks and quality not in ('8k', '8k_hdr'):
                video_tracks = [all_tracks[0]]
            audio, audio_candidates = self._choose_direct_audio(
                data['formats'], failed_audio_keys, required_audio_signature)
            if not video_tracks or not audio:
                debug_log('proxy cache rebuild empty', {
                    'vid': vid, 'quality': quality,
                    'failed_audio_keys': failed_audio_keys or [],
                })
                return None
            cache_key = f'yt_{vid}_{quality}'
            cache_val = {
                'video_tracks': video_tracks,
                'video_url': video_tracks[0]['url'],
                'audio_url': audio['url'],
                'video_item': video_tracks[0],
                'audio_item': audio,
                'audio_candidates': audio_candidates,
                'failed_audio_keys': list(failed_audio_keys or []),
                'duration': data.get('duration') or 0,
                'expires': time.time() + 21600,
            }
            self.setCache(cache_key, cache_val)
            debug_log('proxy cache rebuilt', {
                'vid': vid, 'quality': quality,
                'video_itag': video_tracks[0].get('itag'),
                'audio_itag': audio.get('itag'), 'audio_client': audio.get('client'),
                'audio_codecs': audio.get('codecs'),
            })
            return cache_val
        except Exception as e:
            debug_log('proxy cache rebuild error', {'vid': vid, 'quality': quality, 'error': repr(e)})
            return None

    def _proxy_single(self, params):
        vid = params.get('vid')
        debug_log('proxy single request', {'vid': vid, 'range': params.get('range'), 'keys': sorted(list(params.keys()))[:20]})
        data = self.getCache(f'yt_single_{vid}') if vid else None
        if not data:
            return [404, 'text/plain', '播放缓存已过期或不存在']
        target_url = data.get('url')
        if not target_url:
            return [404, 'text/plain', '播放地址不存在']
        headers = (data.get('headers') or self.header).copy()
        range_header = params.get('range') or params.get('Range')
        if range_header:
            headers['Range'] = range_header
        try:
            r = self.session.get(target_url, headers=headers, stream=True, timeout=30)
            debug_log('proxy single response', {'status': r.status_code, 'content_type': r.headers.get('content-type'), 'content_length': r.headers.get('content-length'), 'content_range': r.headers.get('content-range')})
            content_type = r.headers.get('content-type', 'video/mp4')
            resp_headers = {
                'Content-Type': content_type,
                'Accept-Ranges': 'bytes',
                'Cache-Control': 'no-cache',
            }
            if r.headers.get('content-range'):
                resp_headers['Content-Range'] = r.headers.get('content-range')
            if r.headers.get('content-length'):
                resp_headers['Content-Length'] = r.headers.get('content-length')
            status_code = r.status_code
            body = r.content
            r.close()
            return [status_code, content_type, body, resp_headers]
        except Exception as e:
            debug_log('proxy single error', repr(e))
            return [500, 'text/plain', f'代理播放失败: {str(e)}']

    def _proxy_mpd(self, params):
        vid = params.get('vid')
        quality = params.get('quality') or '1080p'
        data = self.getCache(f'yt_{vid}_{quality}') if vid else None
        if not data:
            debug_log('proxy mpd cache miss, rebuilding', {'vid': vid, 'quality': quality})
            data = self._rebuild_play_cache(vid, quality) if vid else None
        if not data:
            return [404, 'text/plain', '视频缓存已过期或不存在']
        audio_url = data.get('audio_url')
        duration = data.get('duration') or 0
        video_tracks = data.get('video_tracks') or [data.get('video_item') or {}]
        audio_item = data.get('audio_item') or {}
        media_base = f'http://127.0.0.1:9978/proxy?do=py&type=media&vid={vid}&quality={quality}'
        direct_segments = str(self.extendDict.get('seg') or 'proxy').lower() == 'direct'
        duration_pt = f"PT{int(duration or 0)}S"
        mpd = f'''<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="{duration_pt}" minBufferTime="PT1.5S" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">
  <Period id="1" start="PT0S">
'''
        for item in video_tracks:
            init_range = item.get('initRange') or {}
            index_range = item.get('indexRange') or {}
            name = item.get('track_name') or ('HDR' if item.get('is_hdr') else 'SDR')
            base_url = item.get('url') if direct_segments else media_base + f"&track=video&itag={item.get('itag')}"
            mpd += f'''    <AdaptationSet mimeType="{html.escape((item.get('mimeType') or 'video/webm').split(';')[0])}" startWithSAP="1" segmentAlignment="true" scanType="progressive">
      <Representation id="v{item.get('itag', 1)}" bandwidth="{item.get('bitrate', 1000000)}" codecs="{html.escape(item.get('codecs') or '')}" height="{item.get('height', 0)}" width="{item.get('width', 0)}">
        <BaseURL>{html.escape(base_url)}</BaseURL>
        <SegmentBase indexRange="{index_range.get('start', '0')}-{index_range.get('end', '0')}"><Initialization range="{init_range.get('start', '0')}-{init_range.get('end', '0')}"/></SegmentBase>
      </Representation>
    </AdaptationSet>
'''
        if audio_url:
            audio_init = audio_item.get('initRange') or {}
            audio_index = audio_item.get('indexRange') or {}
            audio_base = audio_url if direct_segments else media_base + '&track=audio'
            mpd += f'''    <AdaptationSet mimeType="{html.escape((audio_item.get('mimeType') or 'audio/mp4').split(';')[0])}" startWithSAP="1" segmentAlignment="true" lang="und">
      <Representation id="audio" bandwidth="{audio_item.get('bitrate', 128000)}" codecs="{html.escape(audio_item.get('codecs') or '')}" audioSamplingRate="44100">
        <BaseURL>{html.escape(audio_base)}</BaseURL>
        <SegmentBase indexRange="{audio_index.get('start', '0')}-{audio_index.get('end', '0')}"><Initialization range="{audio_init.get('start', '0')}-{audio_init.get('end', '0')}"/></SegmentBase>
      </Representation>
    </AdaptationSet>
'''
        mpd += '  </Period>\n</MPD>'
        debug_log('proxy mpd tracks', {'vid': vid, 'quality': quality, 'tracks': [{'name': x.get('track_name'), 'itag': x.get('itag')} for x in video_tracks], 'audio': audio_item.get('itag'), 'direct': direct_segments, 'duration': duration_pt})
        return [200, 'application/dash+xml', mpd]

    def _proxy_media(self, params):
        vid = params.get('vid')
        quality = params.get('quality') or '1080p'
        track = params.get('track')
        cache_key = f'yt_{vid}_{quality}'
        data = self.getCache(cache_key) if vid else None
        if not data and vid and track in ('video', 'audio'):
            debug_log('proxy media cache miss, rebuilding', {'vid': vid, 'quality': quality, 'track': track})
            data = self._rebuild_play_cache(vid, quality)
        if not data or track not in ('video', 'audio'):
            return [404, 'text/plain', '媒体不存在']

        def select_item(cache):
            if track == 'video':
                wanted_itag = str(params.get('itag') or '')
                tracks = cache.get('video_tracks') or [cache.get('video_item') or {}]
                item = next((x for x in tracks if str(x.get('itag')) == wanted_itag), tracks[0] if tracks else {})
                return item, item.get('url')
            item = cache.get('audio_item') or {}
            return item, cache.get('audio_url') or item.get('url')

        media_item, target_url = select_item(data)
        if not target_url:
            return [404, 'text/plain', f'{track} 流不存在']
        range_header = params.get('range') or params.get('Range')

        def do_fetch(url, item):
            headers = self.header.copy()
            headers.update((item or {}).get('headers') or {})
            if range_header:
                headers['Range'] = range_header
            return self.session.get(url, headers=headers, stream=True, timeout=30)

        try:
            r = do_fetch(target_url, media_item)
            if r.status_code == 403:
                debug_log('proxy media 403', {
                    'vid': vid, 'quality': quality, 'track': track,
                    'range': range_header, 'itag': media_item.get('itag'),
                    'client': media_item.get('client'), 'codecs': media_item.get('codecs'),
                })
                r.close()
                retried = False
                # 音频先在已缓存的相同 itag/编码候选中切换，避免重复解析。
                if track == 'audio':
                    next_audio = self._next_cached_direct_audio(data, media_item)
                    if next_audio:
                        self.setCache(cache_key, data)
                        media_item = next_audio
                        target_url = next_audio.get('url')
                        r = do_fetch(target_url, media_item)
                        retried = True
                        debug_log('proxy direct audio candidate retried', {
                            'vid': vid, 'itag': media_item.get('itag'),
                            'client': media_item.get('client'), 'status': r.status_code,
                            'range': range_header,
                        })
                if not retried or r.status_code == 403:
                    if retried:
                        r.close()
                    failed = [tuple(x) for x in (data.get('failed_audio_keys') or [])]
                    if track == 'audio':
                        key = self._direct_audio_key(media_item)
                        if key not in failed:
                            failed.append(key)
                    required_signature = (
                        self._direct_audio_signature(data.get('audio_item') or media_item)
                        if track == 'audio' else None)
                    fresh = self._rebuild_play_cache(
                        vid, quality, force_refresh=True,
                        failed_audio_keys=[list(x) for x in failed] if track == 'audio' else None,
                        required_audio_signature=required_signature)
                    if fresh:
                        data = fresh
                        media_item, target_url = select_item(fresh)
                        if target_url:
                            r = do_fetch(target_url, media_item)
                            debug_log('proxy media refreshed retry', {
                                'vid': vid, 'track': track, 'range': range_header,
                                'itag': media_item.get('itag'), 'client': media_item.get('client'),
                                'status': r.status_code,
                            })
            content_type = r.headers.get('content-type', 'application/octet-stream')
            debug_log('proxy media response', {
                'track': track, 'itag': media_item.get('itag'),
                'client': media_item.get('client'), 'codecs': media_item.get('codecs'),
                'track_name': media_item.get('track_name'), 'status': r.status_code,
                'range': range_header, 'content_type': content_type,
                'content_length': r.headers.get('content-length'),
                'content_range': r.headers.get('content-range'),
            })
            resp_headers = {'Content-Type': content_type, 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-cache'}
            if r.headers.get('content-range'):
                resp_headers['Content-Range'] = r.headers.get('content-range')
            if r.headers.get('content-length'):
                resp_headers['Content-Length'] = r.headers.get('content-length')
            status_code = r.status_code
            body = r.content
            r.close()
            return [status_code, content_type, body, resp_headers]
        except Exception as e:
            debug_log('proxy media error', {
                'vid': vid, 'track': track, 'range': range_header, 'error': repr(e),
            })
            return [500, 'text/plain', f'代理媒体失败: {str(e)}']

    def _normalize_category_id(self, cid):
        raw = str(cid or '').strip()
        return CATEGORY_ALIASES.get(raw, raw)

    def _normalize_filter_term(self, value):
        if isinstance(value, (list, tuple)):
            return ' '.join([self._normalize_filter_term(item) for item in value if item])
        if isinstance(value, dict):
            return ' '.join([self._normalize_filter_term(item) for item in value.values() if item])
        return re.sub(r'\s+', ' ', str(value or '')).strip()[:180]

    def _build_category_keyword(self, cid, filters=None):
        category_id = self._normalize_category_id(cid)
        terms = []
        base = CATEGORY_QUERY.get(category_id) or CATEGORY_QUERY.get(str(cid or '').strip()) or category_id or str(cid or '').strip()
        if base:
            terms.append(base)
        if isinstance(filters, dict):
            for value in filters.values():
                term = self._normalize_filter_term(value)
                if term:
                    terms.append(term)
        seen = set()
        output = []
        for term in terms:
            term = term.strip()
            if term and term not in seen:
                seen.add(term)
                output.append(term)
        return ' '.join(output)

    def _search_cache_key(self, key):
        return re.sub(r'\s+', ' ', str(key or '')).strip().lower()

    def _search_youtube(self, key):
        videos, _ = self._search_youtube_page(key, 1)
        return videos

    def _search_youtube_page(self, key, page=1):
        page = max(1, int(page or 1))
        cache_key = self._search_cache_key(key)
        session = self.search_page_cache.get(cache_key)
        if page == 1 or not session:
            session = self._fetch_search_first_page(key)
            self.search_page_cache[cache_key] = session
        while len(session.get('pages', [])) < page and session.get('next'):
            data = self._fetch_search_continuation(session)
            videos = self._extract_videos_from_api(data, 30)
            session.setdefault('pages', []).append(videos)
            session['next'] = self._extract_continuation_token(data)
        pages = session.get('pages', [])
        videos = pages[page - 1] if len(pages) >= page else []
        has_more = bool(session.get('next')) or len(pages) > page
        return videos, has_more

    def _fetch_search_first_page(self, key):
        search_url = f'https://www.youtube.com/results?search_query={quote(str(key or ""))}'
        r = self.session.get(search_url, timeout=10)
        html_str = r.text
        data = self.yt._extract_json_after(html_str, 'ytInitialData') or {}
        ytcfg = self.yt._extract_ytcfg(html_str) or {}
        api_key = ytcfg.get('INNERTUBE_API_KEY') or self.yt._search(r'"INNERTUBE_API_KEY":"([^"]+)"', html_str)
        context = ytcfg.get('INNERTUBE_CONTEXT') or {'client': {'clientName': 'WEB', 'clientVersion': '2.20240310.01.00', 'hl': 'zh-CN', 'gl': 'US'}}
        client = context.get('client') or {}
        return {
            'key': key,
            'api_key': api_key,
            'context': context,
            'client_name': client.get('clientName') or 'WEB',
            'client_version': client.get('clientVersion') or '2.20240310.01.00',
            'referer': search_url,
            'pages': [self._extract_videos_from_api(data, 30)],
            'next': self._extract_continuation_token(data),
        }

    def _fetch_search_continuation(self, session):
        token = session.get('next')
        api_key = session.get('api_key')
        if not token or not api_key:
            return {}
        url = f'https://www.youtube.com/youtubei/v1/search?key={quote(api_key)}'
        headers = self.header.copy()
        headers.update({
            'Content-Type': 'application/json',
            'Origin': 'https://www.youtube.com',
            'Referer': session.get('referer') or 'https://www.youtube.com/',
            'X-YouTube-Client-Name': str(self.yt._client_name_id(session.get('client_name'))),
            'X-YouTube-Client-Version': session.get('client_version') or '2.20240310.01.00',
        })
        payload = {'context': session.get('context') or {}, 'continuation': token}
        r = self.session.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def _extract_continuation_token(self, data):
        tokens = []
        def scan(obj):
            if isinstance(obj, dict):
                endpoint = obj.get('continuationEndpoint') or {}
                token = endpoint.get('continuationCommand', {}).get('token')
                if token:
                    tokens.append(token)
                renderer = obj.get('continuationItemRenderer') or {}
                token = renderer.get('continuationEndpoint', {}).get('continuationCommand', {}).get('token')
                if token:
                    tokens.append(token)
                for value in obj.values():
                    scan(value)
            elif isinstance(obj, list):
                for value in obj:
                    scan(value)
        scan(data)
        return tokens[0] if tokens else ''

    def _extract_videos_fixed(self, html_str, limit=30):
        data = None
        match = re.search(r'var ytInitialData = (\{.*?\});', html_str)
        if match:
            try:
                data = json.loads(match.group(1))
            except Exception:
                data = None
        if not data:
            return []
        return self._extract_videos_from_api(data, limit)

    def _extract_videos_from_api(self, data, limit=30):
        videos = []
        seen = set()
        def scan(obj):
            if len(videos) >= limit:
                return
            if isinstance(obj, dict):
                for key in ('videoRenderer', 'compactVideoRenderer', 'gridVideoRenderer', 'reelItemRenderer'):
                    if key in obj:
                        item = self._parse_renderer(obj[key])
                        if item and item['vod_id'] not in seen:
                            seen.add(item['vod_id'])
                            videos.append(item)
                for value in obj.values():
                    scan(value)
            elif isinstance(obj, list):
                for value in obj:
                    scan(value)
        scan(data)
        return videos[:limit]

    def _parse_renderer(self, renderer):
        try:
            vid = renderer.get('videoId')
            if not vid:
                nav = renderer.get('navigationEndpoint') or {}
                vid = (nav.get('watchEndpoint') or {}).get('videoId')
            if not vid:
                return None
            title_obj = renderer.get('title') or renderer.get('headline') or {}
            title = title_obj.get('simpleText') or ''.join([x.get('text', '') for x in title_obj.get('runs', [])]) or 'YouTube Video'
            dur = (renderer.get('lengthText') or {}).get('simpleText') or 'YouTube'
            return {'vod_id': vid, 'vod_name': html.unescape(title), 'vod_pic': f'http://127.0.0.1:9978/proxy?do=py&type=image&vid={vid}&quality=hqdefault', 'vod_remarks': dur}
        except Exception:
            return None

    def _get_video_title(self, vid):
        try:
            r = self.session.get(f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json', timeout=5)
            return r.json().get('title') or vid
        except Exception:
            return vid

    def _safe_title(self, title):
        if not title:
            return 'video'
        return re.sub(r'[#$@%&!?*|\\/:<>]', ' ', title)[:60]

    def _seconds_to_iso_duration(self, seconds):
        seconds = float(seconds or 0)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds - hours * 3600 - minutes * 60
        parts = []
        if hours:
            parts.append(f'{hours}H')
        if minutes:
            parts.append(f'{minutes}M')
        parts.append(f'{secs:.3f}S')
        return 'PT' + ''.join(parts)

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    def _sabr_client_priority(self):
        configured = self.extendDict.get('sabr_clients') if hasattr(self, 'extendDict') else None
        if isinstance(configured, str):
            configured = [x.strip().upper() for x in configured.split(',') if x.strip()]
        if not isinstance(configured, (list, tuple)):
            configured = ['ANDROID_VR', 'IOS', 'MWEB', 'ANDROID']
        # WEB_INITIAL/WEB are intentionally excluded unless explicitly configured.
        seen = set()
        return [str(x).upper() for x in configured if x and not (str(x).upper() in seen or seen.add(str(x).upper()))]

    def _sabr_quality_videos(self, formats, quality='best'):
        bad_itags = {337, 401}
        configured = self.extendDict.get('sabr_skip_itags') if hasattr(self, 'extendDict') else None
        for value in configured or []:
            if str(value).isdigit():
                bad_itags.add(int(value))
        videos = [
            x for x in (formats or [])
            if x.get('protocol') == 'sabr'
            and x.get('vcodec') != 'none' and x.get('acodec') == 'none'
            and int(x.get('itag') or 0) not in bad_itags
        ]
        if quality in ('8k', '8k_hdr'):
            videos = [x for x in videos if int(x.get('height') or 0) >= 4320]
        elif quality == '4k':
            videos = [x for x in videos if 2160 <= int(x.get('height') or 0) < 4320]
        elif quality == '2k':
            videos = [x for x in videos if 1440 <= int(x.get('height') or 0) < 2160]
        elif quality == '1080p':
            videos = [x for x in videos if 1000 <= int(x.get('height') or 0) < 1440]
        else:
            capped = [x for x in videos if int(x.get('height') or 0) <= 2160]
            videos = capped or videos
        # Keep the proven SABR preference: SDR VP9/H264 before HDR/AV1, then resolution.
        videos.sort(key=lambda x: (
            0 if self.yt._is_hdr_video(x) else 1,
            int(x.get('height') or 0),
            self.yt._video_codec_priority(x),
            int(x.get('bitrate') or 0),
        ), reverse=True)
        return videos, bad_itags

    def _build_sabr_candidates(self, sabr_formats, quality='best'):
        videos, bad_itags = self._sabr_quality_videos(sabr_formats, quality)
        priorities = self._sabr_client_priority()
        candidates = []
        primary_video_sig = None
        primary_audio_sig = None

        def media_signature(item, kind):
            return (
                int(item.get('itag') or 0),
                (item.get('mimeType') or '').split(';')[0].lower(),
                (item.get('codecs') or '').lower(),
                int(item.get('height') or 0) if kind == 'video' else 0,
                int(item.get('width') or 0) if kind == 'video' else 0,
            )

        for client in priorities:
            client_videos = [x for x in videos if str(x.get('client') or '').upper() == client]
            client_audios = [
                x for x in (sabr_formats or [])
                if x.get('protocol') == 'sabr'
                and x.get('vcodec') == 'none' and x.get('acodec') != 'none'
                and str(x.get('client') or '').upper() == client
            ]
            if not client_videos or not client_audios:
                continue
            if primary_video_sig:
                client_videos = [x for x in client_videos if media_signature(x, 'video') == primary_video_sig]
                client_audios = [x for x in client_audios if media_signature(x, 'audio') == primary_audio_sig]
                if not client_videos or not client_audios:
                    debug_log('sabr incompatible fallback skipped', {
                        'client': client, 'required_video': primary_video_sig,
                        'required_audio': primary_audio_sig,
                    })
                    continue
            video = client_videos[0]
            audio = self.yt.choose_audio(client_audios, protocol='sabr', same_client=client)
            if not audio:
                continue
            video_cfg = video.get('_sabr_config') or {}
            audio_cfg = audio.get('_sabr_config') or {}
            # Never mix formats and SABR session data from different player responses.
            if not video_cfg.get('server_abr_streaming_url') or not video_cfg.get('video_playback_ustreamer_config'):
                continue
            if audio_cfg.get('server_abr_streaming_url') != video_cfg.get('server_abr_streaming_url'):
                same_session_audio = next((x for x in client_audios if (
                    (x.get('_sabr_config') or {}).get('server_abr_streaming_url')
                    == video_cfg.get('server_abr_streaming_url'))), None)
                if same_session_audio:
                    audio = same_session_audio
                else:
                    continue
            video_sig = media_signature(video, 'video')
            audio_sig = media_signature(audio, 'audio')
            if primary_video_sig is None:
                primary_video_sig, primary_audio_sig = video_sig, audio_sig
            elif video_sig != primary_video_sig or audio_sig != primary_audio_sig:
                continue
            candidates.append({
                'client': client, 'video_item': video, 'audio_item': audio,
                'video_signature': video_sig, 'audio_signature': audio_sig,
            })
        debug_log('sabr client candidates', {
            'priority': priorities, 'filtered_itags': sorted(bad_itags),
            'candidates': [{
                'client': x['client'], 'video': x['video_item'].get('itag'),
                'audio': x['audio_item'].get('itag'),
                'height': x['video_item'].get('height'),
                'host': urlparse((x['video_item'].get('_sabr_config') or {}).get('server_abr_streaming_url') or '').netloc,
            } for x in candidates],
        })
        return candidates

    def _activate_sabr_candidate(self, vid, data, index, reason='initial'):
        candidates = data.get('sabr_candidates') or []
        if index < 0 or index >= len(candidates):
            return None
        selected = candidates[index]
        video = selected['video_item']
        audio = selected['audio_item']
        state_key = f'{vid}:sabr:{selected.get("client")}:{video.get("itag")}:{audio.get("itag")}'
        self.yt.sabr_state.pop(state_key, None)
        data.update({
            'active_index': index,
            'video_item': video,
            'audio_item': audio,
            'state_key': state_key,
        })
        self.setCache(f'yt_sabr_{vid}', data)
        debug_log('sabr client activated', {
            'vid': vid, 'reason': reason, 'index': index,
            'client': selected.get('client'), 'video': video.get('itag'),
            'audio': audio.get('itag'), 'height': video.get('height'),
            'host': urlparse((video.get('_sabr_config') or {}).get('server_abr_streaming_url') or '').netloc,
        })
        return data

    def _new_sabr_play_data(self, vid, extracted, quality='best'):
        candidates = self._build_sabr_candidates(extracted.get('sabr_formats') or [], quality)
        if not candidates:
            return None
        data = {
            'sabr_candidates': candidates,
            'duration': extracted.get('duration') or 0,
            'expires': time.time() + 1800,
        }
        return self._activate_sabr_candidate(vid, data, 0, reason='initial')

    def _switch_sabr_client(self, vid, failed_index, error):
        with self.sabr_switch_lock:
            current = self.getCache(f'yt_sabr_{vid}') if vid else None
            if not current:
                return None
            failed_index = int(failed_index or 0)
            current_index = int(current.get('active_index') or 0)
            # Parallel audio/video init may already have switched this exact failure.
            if current_index != failed_index:
                debug_log('sabr failover already applied', {
                    'vid': vid, 'failed_index': failed_index,
                    'active_index': current_index,
                })
                return current
            next_index = current_index + 1
            if next_index >= len(current.get('sabr_candidates') or []):
                debug_log('sabr client failover exhausted', {
                    'vid': vid, 'active_index': current_index, 'error': repr(error),
                })
                return None
            old_client = current['sabr_candidates'][current_index].get('client')
            debug_log('sabr client failover', {
                'vid': vid, 'from': old_client,
                'to': current['sabr_candidates'][next_index].get('client'),
                'error': repr(error),
            })
            return self._activate_sabr_candidate(
                vid, current, next_index, reason=f'init failure: {error}')

    def _choose_sabr_video(self, sabr_formats, quality='best'):
        candidates = self._build_sabr_candidates(sabr_formats, quality)
        item = candidates[0]['video_item'] if candidates else None
        debug_log('choose sabr isolated', {
            'client': item.get('client') if item else None,
            'itag': item.get('itag') if item else None,
            'height': item.get('height') if item else None,
            'candidate_count': len(candidates),
        })
        return item

    def _proxy_sabr_mpd(self, params):
        vid = params.get('vid')
        data = self.getCache(f'yt_sabr_{vid}') if vid else None
        if not data:
            debug_log('sabr mpd cache miss rebuild', {'vid': vid})
            try:
                ext = self.yt.extract(vid, force_refresh=True)
                data = self._new_sabr_play_data(vid, ext, 'best')
            except Exception as e:
                debug_log('sabr mpd rebuild error', repr(e))
        if not data or not data.get('video_item') or not data.get('audio_item'):
            return [404, 'text/plain', 'SABR 音视频缓存不存在']

        video = data['video_item']
        audio = data['audio_item']
        duration = int(data.get('duration') or 0)
        duration_pt = f'PT{duration}S' if duration else 'PT0S'
        base = f'http://127.0.0.1:9978/proxy?do=py&amp;type=sabr&amp;vid={html.escape(str(vid))}'
        video_mime = html.escape((video.get('mimeType') or 'video/webm').split(';')[0])
        audio_mime = html.escape((audio.get('mimeType') or 'audio/webm').split(';')[0])
        video_duration_ms = int(float((video.get('_sabr_config') or {}).get('target_duration_sec') or 6) * 1000)
        # YouTube VOD SABR audio segments are normally ~10 seconds (observed in MediaHeader).
        audio_duration_ms = int(float((audio.get('_sabr_config') or {}).get('target_duration_sec') or 10) * 1000)
        if audio_duration_ms < 8000:
            audio_duration_ms = 10000
        mpd = f'''<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="{duration_pt}" minBufferTime="PT2S" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">
  <Period id="1" start="PT0S">
    <AdaptationSet id="1" contentType="video" mimeType="{video_mime}" segmentAlignment="true" startWithSAP="1">
      <Representation id="sabr-v{int(video.get('itag') or 0)}" bandwidth="{int(video.get('bitrate') or 1000000)}" codecs="{html.escape(video.get('codecs') or '')}" width="{int(video.get('width') or 0)}" height="{int(video.get('height') or 0)}">
        <SegmentTemplate timescale="1000" duration="{video_duration_ms}" startNumber="1" initialization="{base}&amp;track=video&amp;seg=init" media="{base}&amp;track=video&amp;seg=$Number$"/>
      </Representation>
    </AdaptationSet>
    <AdaptationSet id="2" contentType="audio" mimeType="{audio_mime}" segmentAlignment="true" startWithSAP="1">
      <Representation id="sabr-a{int(audio.get('itag') or 0)}" bandwidth="{int(audio.get('bitrate') or 128000)}" codecs="{html.escape(audio.get('codecs') or '')}">
        <SegmentTemplate timescale="1000" duration="{audio_duration_ms}" startNumber="1" initialization="{base}&amp;track=audio&amp;seg=init" media="{base}&amp;track=audio&amp;seg=$Number$"/>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>'''
        debug_log('proxy true sabr mpd', {
            'vid': vid, 'video': video.get('itag'), 'audio': audio.get('itag'),
            'client': video.get('client'), 'duration': duration,
            'video_segment_ms': video_duration_ms, 'audio_segment_ms': audio_duration_ms,
        })
        return [200, 'application/dash+xml', mpd]

    def _proxy_sabr(self, params):
        vid = params.get('vid')
        track = params.get('track') or 'video'
        segment = params.get('seg') or 'init'
        data = self.getCache(f'yt_sabr_{vid}') if vid else None
        if not data:
            return [404, 'text/plain', 'SABR 缓存不存在']
        if track not in ('video', 'audio'):
            return [400, 'text/plain', '无效 SABR 轨道']
        max_attempts = 1 + (len(data.get('sabr_candidates') or []) if str(segment) == 'init' else 0)
        last_error = None
        for attempt in range(max_attempts):
            data = self.getCache(f'yt_sabr_{vid}') or data
            request_index = int(data.get('active_index') or 0)
            video_item = data.get('video_item')
            audio_item = data.get('audio_item')
            state_key = data.get('state_key') or f'{vid}:sabr'
            try:
                media, meta = self.yt.sabr_get_segment(
                    video_item, audio_item, track, segment, state_key)
                if media is None:
                    debug_log('sabr segment unavailable', meta)
                    return [500, 'text/plain', 'SABR 分段不可用: ' + json.dumps(meta, ensure_ascii=False, default=str)[:1000]]
                current = self.getCache(f'yt_sabr_{vid}') or data
                current_index = int(current.get('active_index') or 0)
                if str(segment) == 'init' and current_index != request_index:
                    debug_log('sabr stale init discarded', {
                        'vid': vid, 'track': track, 'request_index': request_index,
                        'active_index': current_index,
                    })
                    continue
                item = video_item if track == 'video' else audio_item
                content_type = (item.get('mimeType') or ('video/webm' if track == 'video' else 'audio/webm')).split(';')[0]
                debug_log('proxy true sabr segment', {
                    'vid': vid, 'track': track, 'seg': segment, 'itag': item.get('itag'),
                    'client': item.get('client'), 'len': len(media),
                    'first16': media[:16].hex(), 'request_count': meta.get('request_count'),
                    'status': meta.get('status'), 'attempt': attempt + 1,
                })
                return [200, content_type, media, {
                    'Content-Type': content_type, 'Content-Length': str(len(media)),
                    'Cache-Control': 'private, max-age=30', 'Accept-Ranges': 'none',
                }]
            except Exception as e:
                last_error = e
                client = (video_item or {}).get('client')
                debug_log('proxy true sabr error', {
                    'vid': vid, 'track': track, 'seg': segment,
                    'client': client, 'client_index': request_index,
                    'attempt': attempt + 1, 'error': repr(e),
                })
                can_failover = str(segment) == 'init' and ('SABR HTTP 403' in repr(e) or 'SABR HTTP 4' in repr(e))
                if not can_failover or not self._switch_sabr_client(vid, request_index, e):
                    break
        return [500, 'text/plain', f'SABR 代理失败: {last_error}']
