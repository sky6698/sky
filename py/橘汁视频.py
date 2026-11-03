# -*- coding: utf-8 -*-
# 橘汁视频 TVBox spider — v3 JSON 通道版
#
# 为什么改协议栈:
#   站点 juziapp.hzhcbkj.cn 的 v5 protobuf 通道已在服务端失效, 任何客户端都过不去:
#     POST /api/v5/find/app/zone   -> {"code":100016,"msg":"二级公钥为空,请配置"}
#     POST /api/proto/v5/drama/*   -> {"code":100017,"msg":"二级私钥为空,请配置"}
#   即服务端没有配置二级密钥对, 无法完成 RSA 二次握手与 _secure 报文解封,
#   原版 (华谊同款协议栈) 的 init/详情/列表/搜索/播放全部走不通。
#   同站仍在正常响应的是 v3 JSON 通道, 只需要 publicParams 头, 不校验签名:
#     GET /api/v3/drama/getCategory                    分类
#     GET /api/v3/debug/drama/list/type                分类列表(分页)
#     GET /api/v3/debug/drama/list                     最新
#     GET /api/v3/debug/drama/search                   搜索
#     GET /api/v3/debug/drama/popular?vodIds=          详情(含片源)
#     GET /api/ex/v3/tags/debug/list                   首页推荐专题
#     GET /api/ex/v3/videoParse/test/videoUsableUrl    播放地址解析
#   故本版全部改走这些接口, 且不再依赖 pycryptodome, 任何 TVBox 内核都能直接跑。
#
# 已知限制 (均为站点数据/配置问题, 脚本侧无法绕开):
#   1. 详情接口对每部片只回 1 条片子 (首集或最新集), 站点没有可匿名访问的完整分集接口,
#      因此剧集类只能播这一集; 电影/综艺这类单片不受影响。
#   2. 短剧(24) 全部是 hgdj「独家短剧」源, 播放地址要由 APP 内置解析器产出,
#      TVBox 拿不到直链; 不需要该分类可把 '24' 加进 _SKIP_CATS。
#   3. 动漫(23) 多为 youku/iqiyi 官方页, 已返回 parse=1, 交给内核解析器处理。
import json
import re
import html
import time
import base64
import hashlib
import ssl
import urllib.request
import urllib.parse

try:
    from base.spider import Spider as _Base
except Exception:
    class _Base(object):
        pass

HOST = 'https://juziapp.hzhcbkj.cn'
UA = 'okhttp/3.12.1'
PKG = 'com.mxj.wylcjbxyx'
VC = '3024'
VNAME = '3.0.2.4'
APPNAME = '%E6%A9%98%E6%B1%81'

_CTX = ssl._create_unverified_context()

# 首页/分类页兜底分类 (接口异常时用)
_FALLBACK_CATS = [
    {'type_id': '20', 'type_name': '电影'},
    {'type_id': '21', 'type_name': '剧集'},
    {'type_id': '22', 'type_name': '综艺'},
    {'type_id': '23', 'type_name': '动漫'},
    {'type_id': '24', 'type_name': '短剧'},
    {'type_id': '26', 'type_name': '漫剧'},
]

_SKIP_CATS = ('25', '27')          # 直播 / 文章, 不是片库
_EP_RE = re.compile(r'^第?\s*0*(\d{1,4})\s*[集话期]')
# 解析结果是网页 (需外部解析器) 的特征
_WEB_RE = re.compile(
    r'(?i)(v\.youku\.com|iqiyi\.com/v_|bilibili\.com/video|mgtv\.com/b/'
    r'|v\.qq\.com/x/|\.s?html?(\?|$))')


class Spider(_Base):
    HOST_NAME = '橘汁视频'

    def getName(self):
        return '橘汁视频'

    # ---------------------------------------------------------------- 基础

    def init(self, extend=''):
        self._udid = hashlib.md5(
            ('%s%s' % (time.time(), id(self))).encode()).hexdigest()[:16].upper()
        self._pp = json.dumps({
            'plat': 'android', 'vOs': '16', '_vOsCode': '36', 'vApp': VC,
            'vName': VNAME, 'pkg': PKG, 'appName': APPNAME,
            'udid': self._udid, 'uuid': self._udid, 'chid': '10000',
            'androidID': self._udid, 'net': '1', 'young': 0, 'tenantId': '*',
            'v': 1, 'device': 0, 'lang': 'zh', 'country': 'CN',
            'cpu': 'arm64-v8a',
        }, separators=(',', ':'))
        self._cats = []

    def _json(self, path, params=None, timeout=15):
        """GET v3 JSON 接口, 失败返回 {}。"""
        try:
            url = HOST + path
            if params:
                url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={
                'User-Agent': UA, 'Accept': 'application/json',
                'Cache-Control': 'no-cache', 'publicParams': self._pp})
            raw = urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()
            j = json.loads(raw.decode('utf-8', 'replace'))
            if j.get('code') not in (200, '200'):
                return {}
            return j
        except Exception:
            return {}

    @staticmethod
    def _clean(s):
        if not s:
            return ''
        s = re.sub(r'(?is)<(script|style).*?</\1>', '', str(s))
        s = re.sub(r'(?i)<br\s*/?>|</p>', '\n', s)
        s = re.sub(r'<[^>]+>', '', s)
        s = html.unescape(s).replace('\u00a0', ' ')
        return re.sub(r'\n{2,}', '\n', s).strip()

    @staticmethod
    def _pic(it):
        cov = it.get('coverImage') or {}
        return cov.get('path') or cov.get('thumbnailPath') or ''

    def _vod(self, it):
        """列表项 -> TVBox vod。"""
        year = it.get('year')
        return {
            'vod_id': str(it.get('id') or ''),
            'vod_name': it.get('name') or '',
            'vod_pic': self._pic(it),
            'vod_remarks': it.get('remark') or '',
            'vod_year': str(year) if year else '',
        }

    # ---------------------------------------------------------------- 首页

    def _categories(self):
        if self._cats:
            return self._cats
        cats = []
        j = self._json('/api/v3/drama/getCategory', {'orderBy': 'type_id'})
        for c in (j.get('data') or []):
            cid = str(c.get('id') or '')
            name = (c.get('name') or '').strip()
            if not cid or not name:
                continue
            if cid in _SKIP_CATS or '直播' in name or '文章' in name:
                continue
            cats.append({'type_id': cid, 'type_name': name})
        if not cats:
            cats = [dict(c) for c in _FALLBACK_CATS]
        self._cats = cats
        return cats

    def homeContent(self, f=''):
        cls = [{'type_id': 'new', 'type_name': '最近更新'}]
        cls.extend(self._categories())
        return {'class': cls}

    def homeVideoContent(self):
        rows = []
        seen = set()
        try:
            j = self._json('/api/ex/v3/tags/debug/list', timeout=20)
            for t in (j.get('data') or []):
                for sec in (t.get('sections') or []):
                    for v in (sec.get('vodList') or []):
                        vid = str(v.get('id') or '')
                        if not vid or vid in seen:
                            continue
                        seen.add(vid)
                        rows.append(self._vod(v))
        except Exception:
            rows = []
        if not rows:
            rows = self._list('new', 1)
        return {'list': rows[:150]}

    # ---------------------------------------------------------------- 列表

    def _list(self, tid, pg):
        pg = max(1, int(pg or 1))
        params = {'page': pg, 'pagesize': 30}
        if tid in ('new', 'latest', ''):
            path = '/api/v3/debug/drama/list'
        else:
            path = '/api/v3/debug/drama/list/type'
            params['typeId1'] = tid
        j = self._json(path, params, timeout=20)
        data = j.get('data') or {}
        if isinstance(data, dict):
            items = data.get('list') or []
        else:
            items = data or []
        out = []
        for it in items:
            v = self._vod(it)
            if v['vod_id']:
                out.append(v)
        return out

    def categoryContent(self, tid, pg, f='', ext=''):
        pg = max(1, int(pg or 1))
        if str(tid) == 'history':
            return {'list': [], 'page': 1, 'pagecount': 1,
                    'limit': 30, 'total': 0}
        items = self._list(tid, pg)
        return {'list': items, 'page': pg, 'pagecount': 999,
                'limit': 30, 'total': 99999}

    # ---------------------------------------------------------------- 搜索

    def searchContent(self, key, quick=False, pg=1):
        pg = max(1, int(pg or 1))
        j = self._json('/api/v3/debug/drama/search',
                       {'page': pg, 'pagesize': 24, 'searchKeys': key},
                       timeout=20)
        out = []
        for it in ((j.get('data') or {}).get('list') or []):
            v = self._vod(it)
            if v['vod_id']:
                out.append(v)
        if not out:
            j = self._json('/api/v3/drama/adminList',
                           {'page': pg, 'pagesize': 24, 'vodName': key},
                           timeout=20)
            for it in ((j.get('data') or {}).get('list') or []):
                v = self._vod(it)
                if v['vod_id']:
                    out.append(v)
        return {'list': out, 'page': pg}

    # ---------------------------------------------------------------- 详情

    def _detail_item(self, vid):
        j = self._json('/api/v3/debug/drama/popular', {'vodIds': vid},
                       timeout=20)
        lst = (j.get('data') or {}).get('list') or []
        if lst:
            return lst[0]
        j = self._json('/api/v3/drama/adminList',
                       {'page': 1, 'pagesize': 1, 'vodId': vid}, timeout=20)
        lst = (j.get('data') or {}).get('list') or []
        return lst[0] if lst else None

    @staticmethod
    def _ep_title(v):
        t_old = (v.get('titleOld') or '').strip()
        t = (v.get('title') or '').strip()
        for cand in (t_old, t):
            if not cand:
                continue
            m = _EP_RE.match(cand)
            if m:
                return m.group(1)
            if re.match(r'^\d{1,4}$', cand):
                return str(int(cand))
        return t_old or t or '正片'

    def detailContent(self, ids):
        vid = str(ids[0])
        it = self._detail_item(vid)
        if not it:
            return {'list': [{'vod_id': vid, 'vod_name': vid,
                              'vod_play_from': '橘汁',
                              'vod_play_url': '暂无片源$http://'}]}
        vod = self._vod(it)
        vod['vod_id'] = vid
        vod['vod_type'] = it.get('clazz') or ''
        vod['vod_area'] = it.get('area') or ''
        vod['vod_lang'] = it.get('lang') or ''
        vod['vod_actor'] = it.get('actor') or ''
        vod['vod_director'] = it.get('director') or ''
        vod['vod_content'] = self._clean(it.get('intro') or it.get('brief'))

        lines = {}
        sorts = {}
        for v in (it.get('videos') or []):
            src = v.get('source') or ''
            path = v.get('path') or ''
            if not src or not path:
                continue
            name = v.get('sourceCn') or src
            payload = base64.b64encode(json.dumps(
                {'f': src, 'u': path}, separators=(',', ':')).encode()).decode()
            lines.setdefault(name, []).append(
                '%s$%s' % (self._ep_title(v), payload))
            try:
                s = int(v.get('sort') or 0)
            except Exception:
                s = 0
            if s > sorts.get(name, -1):
                sorts[name] = s

        order = sorted(lines.keys(), key=lambda n: -sorts.get(n, 0))
        if order:
            vod['vod_play_from'] = '$$$'.join(order)
            vod['vod_play_url'] = '$$$'.join(
                '#'.join(lines[n]) for n in order)
        else:
            vod['vod_play_from'] = '橘汁'
            vod['vod_play_url'] = '暂无片源$http://'
        return {'list': [vod]}

    # ---------------------------------------------------------------- 播放

    def _resolve(self, src, path):
        """片源 -> 直链。解析服务偶发把入参原样吐回(等于失败), 故重试一轮。"""
        apis = ('/api/ex/v3/videoParse/test/videoUsableUrl',
                '/api/ex/v3/security/videoUsableUrl')
        for attempt in (0, 1):
            for api in apis:
                j = self._json(api, {'vodPlayFrom': src, 'playUrl': path},
                               timeout=20)
                data = j.get('data')
                if not isinstance(data, dict):
                    continue
                url = (data.get('playUrl') or '').strip()
                if url.lower().startswith('http'):
                    return url, data.get('headers')
            if attempt == 0:
                time.sleep(0.4)
        return '', None

    def playerContent(self, flag, pid, vipFlags=None):
        header = {'User-Agent': UA}
        if not pid:
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': header}
        if pid.startswith('http'):
            return {'parse': 0, 'playUrl': '', 'url': pid, 'header': header}
        src, path = flag or '', pid
        try:
            j = json.loads(base64.b64decode(pid).decode('utf-8'))
            src = j.get('f') or src
            path = j.get('u') or path
        except Exception:
            pass
        url, hdrs = self._resolve(src, path)
        if url and not url.lower().startswith('http'):
            url = ''            # 解析器没给出可播地址(如 hgdj 短剧), 放弃
        if not url and path.startswith('http'):
            url = path          # 该源本身就是直链, 解析失败时直接用
        if isinstance(hdrs, dict):
            for k, v in hdrs.items():
                header[str(k)] = str(v)
        elif isinstance(hdrs, list):
            for h in hdrs:
                if isinstance(h, dict) and h.get('name'):
                    header[str(h['name'])] = str(h.get('value') or '')
        # 腾讯/优酷/爱奇艺等返回的是网页, 交给内核的解析器
        need_parse = 1 if (url and _WEB_RE.search(url)) else 0
        return {'parse': need_parse, 'jx': need_parse,
                'playUrl': '', 'url': url, 'header': header}

    # ---------------------------------------------------------------- 杂项

    def isVideoFormat(self, url):
        return bool(re.search(
            r'(?i)\.(m3u8|mp4|flv|mkv|avi|ts|mov|mpd)(\?|$)', url or ''))

    def isTextFormat(self, url):
        return False

    def destroy(self):
        pass
