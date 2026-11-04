# -*- coding: utf-8 -*-
"""
链路：
  1) 握手 POST /api/v5/find/app/zone
     body = RSARequest{timestamp, randomStr, sign=RSA1(ts+random), fake1, fake2}
     data = RSAPublic{str2..str5}  → 拼接得到二级 RSA 公钥
  2) 业务 POST /api/proto/v5/drama/category | search | getDetail
          POST /api/proto/v5/videoUsableUrl
     头 publicParams = 设备参数 JSON + sig(RSA2(ts+random+vApp)) + sig2/sig3(AES-ECB dataIv)
     体 SecureRequest{aesEncrypt1=random8, aesEncrypt2=B64(AES-ECB(dataKey, query+ts)),
                      aesFakestr=random20, timestamp, randomStr}
  3) 首页 GET /api/v3/drama/getCategory    分类 + 筛选项(converUrl)
          GET /api/ex/v3/security/tag/list 专题（data 用 dataKey、dataIv 两轮 AES-ECB 解密）

要点：
  * 服务端现在只认「明文 publicParams」，不再接受 App 的 paramsData 密文头，故这里不加密请求头。
  * pkg / vApp 必须用该 App 自己的（com.asjdhjhd.mgd.p3 / 3070），
    用别的包名会返回 100016「二级公钥为空,请配置」。
  * AES / RSA 全部为纯 Python 实现，不依赖 pycryptodome，任何 TVBox 内核都能直接跑。
"""

import base64
import json
import random
import re
import ssl
import time
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _Spider
except Exception:
    class _Spider(object):
        pass

# ---------------------------------------------------------------- 站点参数
HOST = 'https://juziapp.hzhcbkj.cn'
UA = 'okhttp/3.12.1'

CONF = {
    'appName': '%E6%A9%98%E6%B1%81',          # 橘汁（URL 编码）
    'publicKey': 'MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCr8SzZhjYy+rsya1K09t8d2K50pWFoBkgUqMpKOiW+3IEVKd4eTdvg9RSOjQ82kypL6R9BnsmrS1V8s4PVDwjQbUtYhTPPC9Hz16qY7rpD6m0d2vr09/UpWQ5uOy9PR0QTrsioveZ+DIe9jc3C+zBCu/kZSY/R8stwJoiitki3gwIDAQAB',
    'dataKey': 'ZU1DSFFWNENKMDYXVUQRN0ZJDUC4PQ==',
    'dataIv': 'OC1A06E197EF10CF3F6058CA7A803B5E',
    'pkg': 'com.asjdhjhd.mgd.p3',
    'version': '3.0.7.0',
    'decrypt': '1',
}

_MEDIA_RE = re.compile(r'(?i)^https?://.*\.(mp4|m3u8|flv|mkv|avi|ts|mov|mpd|m4a|wmv)(\?.*)?$')
_RND_CHARS = '1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
_SSL = ssl._create_unverified_context()


# ---------------------------------------------------------------- AES（纯 Python）
_SBOX = bytes.fromhex(
    '637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0'
    'b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275'
    '09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf'
    'd0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2'
    'cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb'
    'e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08'
    'ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e'
    'e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16'
)
_INV = bytearray(256)
for _i, _v in enumerate(_SBOX):
    _INV[_v] = _i
_INV = bytes(_INV)


def _xt(a):
    a <<= 1
    return (a ^ 0x1b) & 0xff if a & 0x100 else a


def _gmul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xt(a)
        b >>= 1
    return r


# 查表加速：GF(2^8) 乘法表
_M2 = bytes(_gmul(i, 2) for i in range(256))
_M3 = bytes(_gmul(i, 3) for i in range(256))
_M9 = bytes(_gmul(i, 9) for i in range(256))
_M11 = bytes(_gmul(i, 11) for i in range(256))
_M13 = bytes(_gmul(i, 13) for i in range(256))
_M14 = bytes(_gmul(i, 14) for i in range(256))


class AES(object):
    """AES-128/192/256，ECB + PKCS7（纯 Python，查表实现）"""

    def __init__(self, key):
        if len(key) not in (16, 24, 32):
            key = (key + b'0' * 32)[:32] if len(key) < 32 else key[:32]
        self.nr = len(key) // 4 + 6
        self.rk = self._expand(key)

    @staticmethod
    def _expand(key):
        nk = len(key) // 4
        nr = nk + 6
        w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
        rcon = 1
        for i in range(nk, 4 * (nr + 1)):
            t = list(w[i - 1])
            if i % nk == 0:
                t = t[1:] + t[:1]
                t = [_SBOX[x] for x in t]
                t[0] ^= rcon
                rcon = _xt(rcon)
            elif nk > 6 and i % nk == 4:
                t = [_SBOX[x] for x in t]
            w.append([w[i - nk][j] ^ t[j] for j in range(4)])
        return [sum(w[4 * r:4 * r + 4], []) for r in range(nr + 1)]

    def encrypt_block(self, block):
        sb, m2, m3, rk = _SBOX, _M2, _M3, self.rk
        s = [block[i] ^ rk[0][i] for i in range(16)]
        for r in range(1, self.nr):
            t = [sb[s[0]], sb[s[5]], sb[s[10]], sb[s[15]],
                 sb[s[4]], sb[s[9]], sb[s[14]], sb[s[3]],
                 sb[s[8]], sb[s[13]], sb[s[2]], sb[s[7]],
                 sb[s[12]], sb[s[1]], sb[s[6]], sb[s[11]]]
            k = rk[r]
            for c in (0, 4, 8, 12):
                a0, a1, a2, a3 = t[c], t[c + 1], t[c + 2], t[c + 3]
                s[c] = m2[a0] ^ m3[a1] ^ a2 ^ a3 ^ k[c]
                s[c + 1] = a0 ^ m2[a1] ^ m3[a2] ^ a3 ^ k[c + 1]
                s[c + 2] = a0 ^ a1 ^ m2[a2] ^ m3[a3] ^ k[c + 2]
                s[c + 3] = m3[a0] ^ a1 ^ a2 ^ m2[a3] ^ k[c + 3]
        t = [sb[s[0]], sb[s[5]], sb[s[10]], sb[s[15]],
             sb[s[4]], sb[s[9]], sb[s[14]], sb[s[3]],
             sb[s[8]], sb[s[13]], sb[s[2]], sb[s[7]],
             sb[s[12]], sb[s[1]], sb[s[6]], sb[s[11]]]
        k = rk[self.nr]
        return bytes([t[i] ^ k[i] for i in range(16)])

    def decrypt_block(self, block):
        ib, m9, m11, m13, m14, rk = _INV, _M9, _M11, _M13, _M14, self.rk
        k = rk[self.nr]
        s = [block[i] ^ k[i] for i in range(16)]
        for r in range(self.nr - 1, 0, -1):
            t = [ib[s[0]], ib[s[13]], ib[s[10]], ib[s[7]],
                 ib[s[4]], ib[s[1]], ib[s[14]], ib[s[11]],
                 ib[s[8]], ib[s[5]], ib[s[2]], ib[s[15]],
                 ib[s[12]], ib[s[9]], ib[s[6]], ib[s[3]]]
            k = rk[r]
            t = [t[i] ^ k[i] for i in range(16)]
            for c in (0, 4, 8, 12):
                a0, a1, a2, a3 = t[c], t[c + 1], t[c + 2], t[c + 3]
                s[c] = m14[a0] ^ m11[a1] ^ m13[a2] ^ m9[a3]
                s[c + 1] = m9[a0] ^ m14[a1] ^ m11[a2] ^ m13[a3]
                s[c + 2] = m13[a0] ^ m9[a1] ^ m14[a2] ^ m11[a3]
                s[c + 3] = m11[a0] ^ m13[a1] ^ m9[a2] ^ m14[a3]
        t = [ib[s[0]], ib[s[13]], ib[s[10]], ib[s[7]],
             ib[s[4]], ib[s[1]], ib[s[14]], ib[s[11]],
             ib[s[8]], ib[s[5]], ib[s[2]], ib[s[15]],
             ib[s[12]], ib[s[9]], ib[s[6]], ib[s[3]]]
        k = rk[0]
        return bytes([t[i] ^ k[i] for i in range(16)])

    def ecb_encrypt(self, data):
        p = 16 - len(data) % 16
        data = data + bytes([p]) * p
        f = self.encrypt_block
        return b''.join([f(data[i:i + 16]) for i in range(0, len(data), 16)])

    def ecb_decrypt(self, data):
        f = self.decrypt_block
        out = b''.join([f(data[i:i + 16]) for i in range(0, len(data), 16)])
        if out:
            p = out[-1]
            if 1 <= p <= 16 and out[-p:] == bytes([p]) * p:
                out = out[:-p]
        return out


# ---------------------------------------------------------------- RSA（纯 Python）
def _tlv(buf, i):
    tag = buf[i]
    i += 1
    ln = buf[i]
    i += 1
    if ln & 0x80:
        n = ln & 0x7f
        ln = int.from_bytes(buf[i:i + n], 'big')
        i += n
    return tag, buf[i:i + ln], i + ln


def _parse_rsa_key(der):
    """从 SPKI / PKCS#1 DER 中取 (n, e)"""

    def walk(buf):
        items = []
        i = 0
        try:
            while i < len(buf):
                tag, val, i = _tlv(buf, i)
                items.append((tag, val))
        except Exception:
            return None
        ints = [v for t, v in items if t == 0x02]
        if len(ints) >= 2:
            n = int.from_bytes(ints[-2], 'big')
            e = int.from_bytes(ints[-1], 'big')
            if n > 0 and e > 0:
                return n, e
        for t, v in items:
            if t == 0x30:
                r = walk(v)
            elif t == 0x03 and v[:1] == b'\x00':
                r = walk(v[1:])
            else:
                r = None
            if r:
                return r
        return None

    return walk(der)


def _rsa_encrypt(data, key):
    """PKCS#1 v1.5 加密 → base64"""
    n, e = key
    k = (n.bit_length() + 7) // 8
    if len(data) > k - 11:
        data = data[:k - 11]
    ps = bytes(random.randint(1, 255) for _ in range(k - 3 - len(data)))
    em = b'\x00\x02' + ps + b'\x00' + data
    return base64.b64encode(pow(int.from_bytes(em, 'big'), e, n).to_bytes(k, 'big')).decode()


# ---------------------------------------------------------------- protobuf 工具
def _vr(n):
    out = b''
    while True:
        b = n & 0x7f
        n >>= 7
        if n:
            out += bytes([b | 0x80])
        else:
            return out + bytes([b])


def _field(num, wire, payload):
    tag = _vr((num << 3) | wire)
    if wire == 2:
        return tag + _vr(len(payload)) + payload
    return tag + payload


def _pb(buf):
    """解析 protobuf 消息（tag 是 varint，字段号 >= 16 时为多字节）"""
    out = []
    i = 0
    n = len(buf)
    while i < n:
        tag = 0
        sh = 0
        while True:
            if i >= n:
                return out
            b = buf[i]
            i += 1
            tag |= (b & 0x7f) << sh
            sh += 7
            if not b & 0x80:
                break
        fn, wt = tag >> 3, tag & 7
        if fn == 0:
            break
        if wt == 0:
            v = 0
            sh = 0
            while i < n:
                b = buf[i]
                i += 1
                v |= (b & 0x7f) << sh
                sh += 7
                if not b & 0x80:
                    break
            out.append((fn, wt, v))
        elif wt == 2:
            ln = 0
            sh = 0
            while i < n:
                b = buf[i]
                i += 1
                ln |= (b & 0x7f) << sh
                sh += 7
                if not b & 0x80:
                    break
            out.append((fn, wt, buf[i:i + ln]))
            i += ln
        elif wt == 5:
            out.append((fn, wt, buf[i:i + 4]))
            i += 4
        elif wt == 1:
            out.append((fn, wt, buf[i:i + 8]))
            i += 8
        else:
            break
    return out


def _txt(v):
    if isinstance(v, bytes):
        return v.decode('utf-8', 'replace')
    return '' if v is None else str(v)


def _rnd(k):
    return ''.join(random.choice(_RND_CHARS) for _ in range(k - 1)) + '='


class Spider(_Spider):
    HOST_NAME = '橘汁视频'

    def getName(self):
        return '橘汁视频'

    # ------------------------------------------------------------ 初始化
    def init(self, extend=''):
        self.host = HOST
        self.conf = dict(CONF)
        self._load_ext(extend)
        self.vapp = str(self.conf['version']).replace('.', '')
        self.udid = '%016X' % random.getrandbits(64)
        self.rsa1 = _parse_rsa_key(base64.b64decode(self.conf['publicKey']))
        self.rsa2 = None
        self._zone_done = False
        self._zone_at = 0
        self._tags = []
        self._tags_at = 0
        self._zone()

    def _load_ext(self, extend):
        """兼容订阅里 ext 的写法：{publicKey, dataKey, dataIv, pkg, version, host}"""
        if not extend:
            return
        try:
            ext = json.loads(extend) if isinstance(extend, str) else dict(extend)
        except Exception:
            return
        if not isinstance(ext, dict):
            return
        for k in ('publicKey', 'dataKey', 'dataIv', 'pkg', 'version', 'appName'):
            if ext.get(k):
                self.conf[k] = ext[k]
        if ext.get('host'):
            h = str(ext['host']).rstrip('/')
            self.host = h if h.startswith('http') else 'https://' + h

    def _ensure(self):
        """没拿到二级公钥时重试握手（60 秒冷却，避免频繁失败拖慢界面）"""
        if self.rsa2:
            return
        if self._zone_done and time.time() - self._zone_at < 60:
            return
        self._zone()

    # ------------------------------------------------------------ 握手
    def _zone(self):
        self._zone_done = True
        self._zone_at = time.time()
        try:
            ts = int(time.time() * 1000)
            r = _rnd(16)
            sign = _rsa_encrypt((str(ts) + r).encode(), self.rsa1)
            body = (_field(1, 0, _vr(ts)) + _field(2, 2, sign.encode()) +
                    _field(3, 2, r.encode()) + _field(4, 2, r.encode()) +
                    _field(5, 2, r.encode()))
            code, msg, data = self._api('/api/v5/find/app/zone', body)
            if code != 200 or not data:
                return False
            zf = {fn: _txt(v) for fn, wt, v in _pb(data) if wt == 2}
            der = base64.b64decode(''.join(zf[k] for k in (2, 3, 4, 5)))
            self.rsa2 = _parse_rsa_key(der)
            return self.rsa2 is not None
        except Exception:
            return False

    # ------------------------------------------------------------ HTTP
    def _params(self, signed):
        p = {'plat': 'android', 'vOs': '16', '_vOsCode': '36', 'vApp': self.vapp,
             'vName': self.conf['version'], 'pkg': self.conf['pkg'],
             'appName': self.conf.get('appName') or '%E6%A9%98%E6%B1%81',
             'udid': self.udid, 'uuid': self.udid, 'chid': '10000',
             'androidID': self.udid, 'net': '1', 'young': 0, 'tenantId': '*',
             'v': 1, 'device': 0, 'lang': 'zh', 'country': 'CN', 'cpu': 'arm64-v8a'}
        if signed and self.rsa2:
            ts = int(time.time() * 1000)
            r = _rnd(16)
            p['sig'] = _rsa_encrypt((str(ts) + r + self.vapp).encode(), self.rsa2)
            p['timestamp'] = ts
            p['random_str'] = r
            a = base64.b64encode(AES(self.conf['dataIv'].encode()).ecb_encrypt(
                (str(ts) + r).encode())).decode()
            p['sig2'] = a[:8]
            p['sig3'] = a[8:]
        return json.dumps(p, separators=(',', ':'))

    def _request(self, path, body=None, signed=False, accept='application/x-protobuf'):
        req = urllib.request.Request(self.host + path, data=body)
        # 直接写 headers 字典，避免 urllib 把 publicParams 改名成 Publicparams
        hdr = {'User-Agent': UA, 'Accept': accept, 'publicParams': self._params(signed)}
        if body is not None:
            hdr['Content-Type'] = 'application/x-protobuf'
        req.headers = hdr
        return urllib.request.urlopen(req, timeout=20, context=_SSL).read()

    def _api(self, path, body):
        return self._parse_result(self._request(path, body, signed=False))

    def _proto(self, path, params):
        self._ensure()
        if not self.rsa2:
            return 0, 'no zone', b''
        ts = int(time.time() * 1000)
        r8 = _rnd(8)
        r20 = _rnd(20)
        qs = '&'.join('%s=%s' % (k, v) for k, v in params.items()
                      if v is not None and str(v) != '')
        enc = base64.b64encode(AES(self.conf['dataKey'].encode()).ecb_encrypt(
            (qs + str(ts)).encode())).decode()
        body = (_field(1, 2, r8.encode()) + _field(2, 2, enc.encode()) +
                _field(3, 2, r20.encode()) + _field(4, 0, _vr(ts)) +
                _field(5, 2, r8.encode()))
        return self._parse_result(self._request(path, body, signed=True))

    @staticmethod
    def _parse_result(raw):
        code, msg, data = 0, '', b''
        for fn, wt, v in _pb(raw):
            if fn == 1 and wt == 0:
                code = v
            elif fn == 2 and wt == 2:
                msg = _txt(v)
            elif fn == 3 and wt == 2:
                data = v
        return code, msg, data

    def _json_get(self, path):
        return json.loads(self._request(path, None, signed=False, accept='application/json'))

    # ------------------------------------------------------------ 数据转换
    @staticmethod
    def _cover(raw):
        for fn, wt, v in _pb(raw):
            if fn in (1, 2) and wt == 2:
                s = _txt(v)
                if s.startswith('http'):
                    return s
        return ''

    def _bean(self, raw):
        s, n = {}, {}
        for fn, wt, v in _pb(raw):
            if wt == 2:
                s[fn] = v
            elif wt == 0:
                n[fn] = v
        return {'vod_id': str(n.get(3) or ''),
                'vod_name': _txt(s.get(5)),
                'vod_pic': self._cover(s.get(2) or b''),
                'vod_remarks': _txt(s.get(13)),
                'vod_year': str(n.get(14) or ''),
                'vod_area': _txt(s.get(1))}

    def _list(self, data):
        out, seen = [], set()
        for fn, wt, v in _pb(data):
            if fn == 1 and wt == 2:
                it = self._bean(v)
                if it['vod_id'] and it['vod_id'] not in seen:
                    seen.add(it['vod_id'])
                    out.append(it)
        return out

    # ------------------------------------------------------------ 首页
    def homeContent(self, filter):
        cats, filters = [], {}
        try:
            j = self._json_get('/api/v3/drama/getCategory?orderBy=type_id')
            for c in (j.get('data') or []):
                name = c.get('name') or ''
                if not name or name in ('公告', '文章'):   # 公告/文章不是片库
                    continue
                tid = str(c.get('id'))
                cats.append({'type_id': tid, 'type_name': name})
                f = self._filters(c.get('converUrl'))
                if f:
                    filters[tid] = f
        except Exception:
            pass
        if not cats:
            cats = [{'type_id': '20', 'type_name': '电影'},
                    {'type_id': '21', 'type_name': '剧集'},
                    {'type_id': '22', 'type_name': '综艺'},
                    {'type_id': '23', 'type_name': '动漫'},
                    {'type_id': '24', 'type_name': '短剧'},
                    {'type_id': '26', 'type_name': '漫剧'}]
        return {'class': cats, 'filters': filters}

    @staticmethod
    def _filters(conver):
        if not conver:
            return {}
        try:
            obj = json.loads(conver) if isinstance(conver, str) else conver
        except Exception:
            return {}
        out = {}
        for key in ('class', 'lang', 'area', 'year', 'extend_sort'):
            val = (obj or {}).get(key) or ''
            if not val:
                continue
            vals = [{'n': x, 'v': x} for x in str(val).split(',') if x]
            if vals:
                out[key] = vals
        return out

    def homeVideoContent(self):
        # 专题数据 120KB 且要两轮 AES 解密，缓存 10 分钟
        if self._tags and time.time() - self._tags_at < 600:
            return {'list': list(self._tags)}
        vids, seen = [], set()
        try:
            j = self._json_get('/api/ex/v3/security/tag/list')
            data = j.get('data')
            if isinstance(data, str) and data:
                data = self._decrypt_json(data)
            if isinstance(data, str):
                data = json.loads(data)
            for tag in (data or []):
                for sec in (tag.get('sections') or []):
                    for v in (sec.get('vodList') or []):
                        vid = str(v.get('id') or '')
                        if not vid or vid in seen:
                            continue
                        seen.add(vid)
                        cov = v.get('coverImage') or {}
                        vids.append({'vod_id': vid,
                                     'vod_name': v.get('name') or '',
                                     'vod_pic': cov.get('path') or cov.get('thumbnailPath') or '',
                                     'vod_remarks': v.get('remark') or ''})
        except Exception:
            pass
        if vids:
            self._tags = vids
            self._tags_at = time.time()
        return {'list': vids}

    def _decrypt_json(self, data):
        """专题接口 data：先用 dataKey 再用 dataIv 做 AES-ECB 解密"""
        try:
            s = data
            for k in (self.conf['dataKey'], self.conf['dataIv']):
                s = AES(k.encode()).ecb_decrypt(base64.b64decode(s)).decode('utf-8', 'replace')
            return s
        except Exception:
            return data

    # ------------------------------------------------------------ 分类
    _MAP = {'class': 'vodClass', 'lang': 'vodLang', 'area': 'vodArea',
            'year': 'vodYear', 'extend_sort': 'vodOrderBy'}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        out = []
        try:
            self._ensure()
            if self.rsa2:
                p = {'pagesize': 21, 'typeId1': tid, 'page': pg}
                for k, v in (extend or {}).items():
                    if k in self._MAP and v:
                        p[self._MAP[k]] = v
                code, msg, data = self._proto('/api/proto/v5/drama/category', p)
                if code == 200:
                    out = self._list(data)
            if not out:
                out = self._v3_list('/api/v3/debug/drama/list/type?page=%d&pagesize=24&typeId1=%s'
                                    % (pg, tid))
        except Exception:
            pass
        return {'list': out, 'page': pg, 'pagecount': pg if len(out) < 21 else pg + 1,
                'limit': 21, 'total': 99999}

    def _v3_list(self, path):
        try:
            j = self._json_get(path)
            out = []
            for it in ((j.get('data') or {}).get('list') or []):
                cov = it.get('coverImage') or {}
                out.append({'vod_id': str(it.get('id') or ''),
                            'vod_name': it.get('name') or '',
                            'vod_pic': cov.get('path') or '',
                            'vod_remarks': it.get('remark') or ''})
            return out
        except Exception:
            return []

    # ------------------------------------------------------------ 详情
    def detailContent(self, ids):
        vid = str(ids[0]) if ids else ''
        vod = {'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_content': '',
               'vod_play_from': '', 'vod_play_url': ''}
        try:
            code, msg, data = self._proto('/api/proto/v5/drama/getDetail', {'id': vid})
            if code != 200 or not data:
                return {'list': [self._detail_v3(vid)]}
            fields, vids = {}, []
            for fn, wt, v in _pb(data):
                if fn == 29 and wt == 2:
                    vids.append(v)
                elif wt == 2:
                    fields.setdefault(fn, v)
                elif wt == 0:
                    fields.setdefault(fn, v)
            vod['vod_name'] = _txt(fields.get(9))
            vod['vod_pic'] = self._cover(fields.get(2) or b'')
            vod['vod_area'] = _txt(fields.get(1))
            vod['vod_year'] = _txt(fields.get(18))
            vod['vod_actor'] = _txt(fields.get(25)).strip(' ,')
            vod['vod_director'] = _txt(fields.get(12))
            vod['vod_remarks'] = _txt(fields.get(26))
            vod['type_name'] = _txt(fields.get(13))
            intro = re.sub(r'<[^>]+>', '', _txt(fields.get(6))).strip()
            vod['vod_content'] = intro or _txt(fields.get(7))
            vod['vod_play_from'], vod['vod_play_url'] = self._play(vids)
            if not vod['vod_play_from']:
                return {'list': [self._detail_v3(vid)]}
        except Exception:
            return {'list': [self._detail_v3(vid)]}
        return {'list': [vod]}

    def _play(self, vids):
        lines, order = [], {}
        for raw in vids:
            f = {}
            for fn, wt, v in _pb(raw):
                if wt == 2:
                    f[fn] = _txt(v)
            path = f.get(4) or ''
            if not path:
                continue
            src = f.get(9) or ''
            name = f.get(10) or src or '橘汁'
            title = f.get(2) or f.get(3) or ('第%s集' % _txt(f.get(1)))
            if _MEDIA_RE.match(path):
                url = path
            else:
                url = base64.b64encode(json.dumps(
                    {'vodPlayFrom': src, 'playUrl': path},
                    separators=(',', ':')).encode()).decode()
            if name not in order:
                order[name] = []
                lines.append(name)
            order[name].append('%s$%s' % (title, url))
        return ('$$$'.join(lines),
                '$$$'.join('#'.join(order[n]) for n in lines))

    def _detail_v3(self, vid):
        """兜底：v3 接口（每部片只有 1 条 videos）"""
        vod = {'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_content': '',
               'vod_play_from': '', 'vod_play_url': ''}
        try:
            j = self._json_get('/api/v3/debug/drama/popular?vodIds=%s' % vid)
            lst = ((j.get('data') or {}).get('list') or [])
            if not lst:
                return vod
            it = lst[0]
            vod['vod_name'] = it.get('name') or ''
            vod['vod_pic'] = (it.get('coverImage') or {}).get('path') or ''
            vod['vod_remarks'] = it.get('remark') or ''
            vod['vod_content'] = re.sub(r'<[^>]+>', '', it.get('intro') or '')
            froms, urls = [], []
            for v in (it.get('videos') or []):
                src = v.get('source') or ''
                name = v.get('sourceCn') or src or '橘汁'
                path = v.get('path') or ''
                if not path:
                    continue
                title = v.get('title') or '正片'
                if _MEDIA_RE.match(path):
                    u = path
                else:
                    u = base64.b64encode(json.dumps(
                        {'vodPlayFrom': src, 'playUrl': path},
                        separators=(',', ':')).encode()).decode()
                froms.append(name)
                urls.append('%s$%s' % (title, u))
            vod['vod_play_from'] = '$$$'.join(froms)
            vod['vod_play_url'] = '$$$'.join(urls)
        except Exception:
            pass
        return vod

    # ------------------------------------------------------------ 搜索
    def searchContent(self, key, quick, pg='1'):
        self._ensure()
        out = []
        try:
            if self.rsa2:
                code, msg, data = self._proto('/api/proto/v5/drama/search',
                                              {'searchKeys': key, 'page': pg, 'pagesize': 21})
                if code == 200:
                    out = self._list(data)
            if not out:
                out = self._v3_list('/api/v3/debug/drama/search?page=%s&pagesize=24&searchKeys=%s'
                                    % (pg, urllib.parse.quote(key)))
        except Exception:
            pass
        return {'list': out}

    # ------------------------------------------------------------ 播放
    def playerContent(self, flag, pid, vipFlags):
        url = pid or ''
        header = {}
        if url.startswith('http'):
            return {'parse': 0, 'playUrl': '', 'url': url, 'header': header}
        try:
            obj = json.loads(base64.b64decode(url).decode('utf-8'))
            src = obj.get('vodPlayFrom') or flag or ''
            path = obj.get('playUrl') or ''
            code, msg, data = self._proto('/api/proto/v5/videoUsableUrl',
                                          {'vodPlayFrom': src, 'playUrl': path})
            if code == 200 and data:
                real = ''
                for fn, wt, v in _pb(data):
                    if fn == 1 and wt == 2:
                        real = _txt(v)
                    elif fn == 6 and wt == 2:
                        kv = {}
                        for a, b, c in _pb(v):
                            if a in (1, 2) and b == 2:
                                kv[a] = _txt(c)
                        if 1 in kv and 2 in kv:
                            header[kv[1]] = kv[2]
                if real:
                    return {'parse': 0, 'playUrl': '', 'url': real, 'header': header}
            if path.startswith('http'):
                return {'parse': 0, 'playUrl': '', 'url': path, 'header': header}
        except Exception:
            pass
        return {'parse': 1, 'playUrl': '', 'url': url, 'header': header}
