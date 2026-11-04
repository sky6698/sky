# -*- coding: utf-8 -*-
import base64
import hashlib
import json
import math
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
HOST = 'https://api.8utdtcq.com'
UA = 'okhttp/3.12.0'
APP_TOKEN = ('1be86e8e18a9fa18b2b8d5432699dad0.ac008ed650fd087bfbecf2fda9d82e9835253ef24843e6b18'
             'fcd128b10763497bcf9d53e959f5377cde038c20ccf9d17f604c9b8bb6e61041def86729b2fc7408bd24'
             '1e23c213ac57f0226ee656e2bb0a583ae0e4f3bf6c6ab6c490c9a6f0d8cdfd366aacf5d83193671a8f77'
             'cd1af1ff2e9145de92ec43ec87cf4bdc563f6e919fe32861b0e93b118ec37d8035fbb3c'
             '.59dd05c5d9a8ae726528783128218f15fe6f2c0c8145eddab112b374fcfe3d79')
BODY_KEY = 'MIICdgIBADANBgkqhkiG9w0BAQEFAASCAmAwggJcAgEAAoGAe6hKrWLi1zQmjTT1ozbE4QdFeJGNxubxld6GrFGximxfMsMB6BpJhpcTouAqywAFppiKetUBBbXwYsYU1wNr648XVmPmCMCy4rY8vdliFnbMUj086DU6Z+/oXBdWU3/b1G0DN3E9wULRSwcKZT3wj/cCI1vsCm3gj2R5SqkA9Y0CAwEAAQKBgAJH+4CxV0/zBVcLiBCHvSANm0l7HetybTh/j2p0Y1sTXro4ALwAaCTUeqdBjWiLSo9lNwDHFyq8zX90+gNxa7c5EqcWV9FmlVXr8VhfBzcZo1nXeNdXFT7tQ2yah/odtdcx+vRMSGJd1t/5k5bDd9wAvYdIDblMAg+wiKKZ5KcdAkEA1cCakEN4NexkF5tHPRrR6XOY/XHfkqXxEhMqmNbB9U34saTJnLWIHC8IXys6Qmzz30TtzCjuOqKRRy+FMM4TdwJBAJQZFPjsGC+RqcG5UvVMiMPhnwe/bXEehShK86yJK/g/UiKrO87h3aEu5gcJqBygTq3BBBoH2md3pr/W+hUMWBsCQQChfhTIrdDinKi6lRxrdBnn0Ohjg2cwuqK5zzU9p/N+S9x7Ck8wUI53DKm8jUJE8WAG7WLj/oCOWEh+ic6NIwTdAkEAj0X8nhx6AXsgCYRql1klbqtVmL8+95KZK7PnLWG/IfjQUy3pPGoSaZ7fdquG8bq8oyf5+dzjE/oTXcByS+6XRQJAP/5ciy1bL3NhUhsaOVy55MHXnPjdcTX0FaLi+ybXZIfIQ2P4rb19mVq1feMbCXhz+L1rG8oat5lYKfpe8k83ZA=='
AES_KEY = b'mvXBSW7ekreItNsT'
AES_IV = b'2U3IrJL8szAKp0Fj'
SIGN_TAIL = '*&zvdvdvddbfikkkumtmdwqppp?|4Y!s!2br'

# 每个接口的 keys 不一样，服务端会校验
KEYS = {
    'list': ('qDpotE2bedimK3QGqlyV5ieXXC3EhaPLQ+IOJyHnHflCj5w/7ESK7FgywMvrgjxbx0GklEFLI4+JshgySe633OIR'
             'stuktwdiCy3CT+fLSpuxBJDIlfXQDaeH3ig1wiB0JsZ601XHiFweGMu4tZfnSpHg3OnoL6nz/uurUif2OK4='),
    'detail': ('Qmxi5ciWXbQzkr7o+SUNiUuQxQEf8/AVyUWY4T/BGhcXBIUz4nOyHBGf9A4KbM0iKF3yp9M7WAY0rrs5PzdTAOB4'
               '5plcS2zZ0wUibcXuGJ29VVGRWKGwE9zu2vLwhfgjTaaDpXo4rby+7GxXTktzJmxvneOUdYeHi+PZsThlvPI='),
    'play': ('ZH8gpdp9bxjuG2NK97sol3o7Uiz+9eVEaVMlE2Fk3j7EResM3YHnECZUH7BONNTjpy7RVNi/YimGuNYriC7Cmswv4P'
             'NYiFYzw9QhlqZKwNfCM6IUpFZ0T4rZx8G78zkv2tNVbfYC4qNQedGi07nWZ33dlSuVxROVfY5JxOWHMI0='),
}

HEADERS = {
    'Cache-Control': 'no-cache',
    'Version': '2406025',
    'PackageName': 'com.uf076bf0c246.qe439f0d5e.m8aaf56b725a.ifeb647346f',
    'Ver': '1.9.2',
    'Referer': HOST,
    'X-Customer-Client-Ip': '127.0.0.1',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Connection': 'Keep-Alive',
    'User-Agent': UA,
}

CATES = [('电影', '1'), ('电视剧', '2'), ('综艺', '3'), ('动漫', '4'), ('短剧', '64')]

# 分类默认二级子类（服务端 sub 参数）
DEFAULT_SUB = {'1': '5', '2': '12', '4': '30', '3': '22', '64': ''}

FILTERS = {
    'area': [('全部', '0'), ('大陆', '大陆'), ('香港', '香港'), ('台湾', '台湾'),
             ('欧美', '俄罗斯,加拿大,德国,意大利,法国,欧美,美国,英国,西班牙'),
             ('日本', '日本'), ('韩国', '韩国'), ('东南亚', '印度,新加坡,泰国,马来西亚'), ('其他', '其他')],
    'year': [('全部', '0'), ('2026', '2026'), ('2025', '2025'), ('2024', '2024'), ('2023', '2023'),
             ('2022', '2022'), ('2021', '2021'), ('2020', '2020'), ('2019', '2019'),
             ('10-15年', '2015,2014,2013,2012,2011,2010'), ('00年代', '2000,2001,2002,2003,2004,2005'),
             ('90年代', '1990,1991,1992,1993,1994,1995'), ('更早', '2')],
}

# ---------------------------------------------------------------- AES-128-CBC（纯 Python）
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
    return r & 0xff


def _rotl8(x, n):
    return ((x << n) | (x >> (8 - n))) & 0xff


def _build_sbox():
    box = [0] * 256
    p = q = 1
    while True:
        p = (p ^ ((p << 1) & 0xff) ^ (0x1b if p & 0x80 else 0)) & 0xff
        q ^= (q << 1) & 0xff
        q ^= (q << 2) & 0xff
        q ^= (q << 4) & 0xff
        q &= 0xff
        if q & 0x80:
            q ^= 0x09
        x = q ^ _rotl8(q, 1) ^ _rotl8(q, 2) ^ _rotl8(q, 3) ^ _rotl8(q, 4)
        box[p] = x ^ 0x63
        if p == 1:
            break
    box[0] = 0x63
    return box


_SBOX = _build_sbox()
_INV = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV[_v] = _i


class AES128(object):
    """AES-128，ECB 块操作 + CBC 封装（与 CryptoJS.AES/CBC/Pkcs7 一致）"""

    def __init__(self, key, iv=None):
        if len(key) != 16:
            raise ValueError('key must be 16 bytes')
        self.iv = iv
        self.rk = self._expand(key)

    @staticmethod
    def _expand(key):
        w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
        rcon = 1
        for i in range(4, 44):
            t = list(w[i - 1])
            if i % 4 == 0:
                t = t[1:] + t[:1]
                t = [_SBOX[x] for x in t]
                t[0] ^= rcon
                rcon = _xt(rcon)
            w.append([w[i - 4][j] ^ t[j] for j in range(4)])
        return [sum(w[4 * r:4 * r + 4], []) for r in range(11)]

    def enc_block(self, b):
        sb = _SBOX
        s = [b[i] ^ self.rk[0][i] for i in range(16)]
        for r in range(1, 10):
            t = [sb[x] for x in s]
            s = [t[4 * ((c + row) % 4) + row] for c in range(4) for row in range(4)]
            k = self.rk[r]
            for c in range(4):
                i = 4 * c
                a0, a1, a2, a3 = s[i], s[i + 1], s[i + 2], s[i + 3]
                s[i] = _xt(a0) ^ (_xt(a1) ^ a1) ^ a2 ^ a3 ^ k[i]
                s[i + 1] = a0 ^ _xt(a1) ^ (_xt(a2) ^ a2) ^ a3 ^ k[i + 1]
                s[i + 2] = a0 ^ a1 ^ _xt(a2) ^ (_xt(a3) ^ a3) ^ k[i + 2]
                s[i + 3] = (_xt(a0) ^ a0) ^ a1 ^ a2 ^ _xt(a3) ^ k[i + 3]
        t = [sb[x] for x in s]
        s = [t[4 * ((c + row) % 4) + row] for c in range(4) for row in range(4)]
        k = self.rk[10]
        return bytes([s[i] ^ k[i] for i in range(16)])

    def dec_block(self, b):
        ib = _INV
        k = self.rk[10]
        s = [b[i] ^ k[i] for i in range(16)]
        for r in range(9, 0, -1):
            t = [s[4 * ((c - row) % 4) + row] for c in range(4) for row in range(4)]
            t = [ib[x] for x in t]
            k = self.rk[r]
            t = [t[i] ^ k[i] for i in range(16)]
            for c in range(4):
                i = 4 * c
                a0, a1, a2, a3 = t[i], t[i + 1], t[i + 2], t[i + 3]
                s[i] = _gmul(a0, 14) ^ _gmul(a1, 11) ^ _gmul(a2, 13) ^ _gmul(a3, 9)
                s[i + 1] = _gmul(a0, 9) ^ _gmul(a1, 14) ^ _gmul(a2, 11) ^ _gmul(a3, 13)
                s[i + 2] = _gmul(a0, 13) ^ _gmul(a1, 9) ^ _gmul(a2, 14) ^ _gmul(a3, 11)
                s[i + 3] = _gmul(a0, 11) ^ _gmul(a1, 13) ^ _gmul(a2, 9) ^ _gmul(a3, 14)
        t = [s[4 * ((c - row) % 4) + row] for c in range(4) for row in range(4)]
        t = [ib[x] for x in t]
        k = self.rk[0]
        return bytes([t[i] ^ k[i] for i in range(16)])

    def cbc_encrypt(self, data):
        p = 16 - len(data) % 16
        data = data + bytes([p]) * p
        out, prev = [], self.iv
        for i in range(0, len(data), 16):
            blk = bytes([data[i + j] ^ prev[j] for j in range(16)])
            prev = self.enc_block(blk)
            out.append(prev)
        return b''.join(out)

    def cbc_decrypt(self, data):
        out, prev = [], self.iv
        for i in range(0, len(data), 16):
            blk = data[i:i + 16]
            dec = self.dec_block(blk)
            out.append(bytes([dec[j] ^ prev[j] for j in range(16)]))
            prev = blk
        raw = b''.join(out)
        if raw:
            p = raw[-1]
            if 1 <= p <= 16 and raw[-p:] == bytes([p]) * p:
                raw = raw[:-p]
        return raw


# ---------------------------------------------------------------- RSA 私钥解密（PKCS#1 v1.5）
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


def _rsa_priv(der):
    """从 PKCS#8 / PKCS#1 私钥 DER 里取 (n, d)"""
    def walk(buf, depth=0):
        if depth > 4:
            return None
        items, i = [], 0
        try:
            while i < len(buf):
                tag, val, i = _tlv(buf, i)
                items.append((tag, val))
        except Exception:
            return None
        ints = [v for t, v in items if t == 0x02]
        if len(ints) >= 9:                       # PKCS#1 RSAPrivateKey
            return (int.from_bytes(ints[1], 'big'), int.from_bytes(ints[3], 'big'))
        for t, v in items:
            if t == 0x30:
                r = walk(v, depth + 1)
            elif t == 0x04:
                r = walk(v, depth + 1)
            else:
                r = None
            if r:
                return r
        return None
    return walk(der)


_PRIV = _rsa_priv(base64.b64decode(BODY_KEY))


def rsa_decrypt_b64(cipher_b64):
    """用内置私钥做 PKCS#1 v1.5 解密，返回明文字节"""
    if not _PRIV:
        return b''
    n, d = _PRIV
    k = (n.bit_length() + 7) // 8
    c = int.from_bytes(base64.b64decode(cipher_b64), 'big')
    em = pow(c, d, n).to_bytes(k, 'big')
    if not em or em[0] != 0 or em[1] != 2:
        return b''
    idx = em.find(b'\x00', 2)
    return em[idx + 1:] if idx > 0 else b''


# ---------------------------------------------------------------- Spider
class Spider(_Spider):
    HOST_NAME = '瓜子影视'

    def getName(self):
        return '瓜子影视'

    def init(self, extend=''):
        self.extend = extend or ''
        self._cache = {}

    # ------------------------------------------------------------ 网络
    def _http(self, url, body):
        req = urllib.request.Request(url, data=body.encode('utf-8'), method='POST')
        # 直接赋值绕过 urllib 的 header capitalize（服务端按原样校验）
        req.headers = dict(HEADERS)
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            return r.read().decode('utf-8', 'replace')

    def _sign(self, request_key_hex, t, keys, upper):
        raw = ('token_id=,token=%s,phone_type=1,request_key=%s,app_id=1,time=%s,keys=%s%s'
               % (APP_TOKEN, request_key_hex, t, keys, SIGN_TAIL))
        sig = hashlib.md5(raw.encode('utf-8')).hexdigest()
        return sig.upper() if upper else sig

    def _post(self, path, payload, keyname='list', upper=True, tries=2):
        last = None
        for _ in range(tries):
            try:
                t = str(int(time.time()))
                enc = AES128(AES_KEY, AES_IV).cbc_encrypt(
                    json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hex().upper()
                keys = KEYS[keyname]
                body = ('token=%s&token_id=&phone_type=1&time=%s&phone_model=xiaomi-22021211rc'
                        '&keys=%s&request_key=%s&signature=%s&app_id=1&ad_version=1'
                        % (APP_TOKEN, t, urllib.parse.quote(keys, safe=''), enc,
                           self._sign(enc, t, keys, upper)))
                txt = self._http(HOST + path, body)
                js = json.loads(txt)
                if str(js.get('code')) != '200':
                    last = 'code=%s msg=%s' % (js.get('code'), str(js.get('msg'))[:80])
                    time.sleep(0.6)
                    continue
                data = js.get('data') or {}
                rk = data.get('response_key')
                if not rk:
                    return data
                kv = json.loads(rsa_decrypt_b64(data.get('keys') or '').decode('utf-8'))
                aes = AES128(kv['key'].encode('utf-8'), kv['iv'].encode('utf-8'))
                return json.loads(aes.cbc_decrypt(bytes.fromhex(rk)).decode('utf-8', 'replace'))
            except Exception as e:
                last = '%s: %s' % (type(e).__name__, e)
                time.sleep(0.6)
        if last:
            self.log('瓜子 %s 失败 %s' % (path, last))
        return {}

    # ------------------------------------------------------------ 数据转换
    @staticmethod
    def _videos(lst):
        out = []
        for v in lst or []:
            cont = str(v.get('vod_continu') or '0')
            out.append({
                'vod_id': str(v.get('vod_id')),
                'vod_name': v.get('vod_name') or '',
                'vod_pic': v.get('vod_pic') or '',
                'vod_remarks': ('更新至%s集' % cont) if cont not in ('0', '') else '电影',
                'vod_year': str(v.get('vod_year') or ''),
                'vod_area': v.get('vod_area') or '',
            })
        return out

    def _filters(self):
        return [{'key': k, 'name': {'area': '地区', 'year': '年份'}[k],
                 'value': [{'n': n, 'v': v} for n, v in vals]} for k, vals in
                (('area', FILTERS['area']), ('year', FILTERS['year']))]

    # ------------------------------------------------------------ 首页 / 分类
    def homeContent(self, filter):
        classes = [{'type_name': n, 'type_id': i} for n, i in CATES]
        return {'class': classes, 'filters': {i: self._filters() for _, i in CATES},
                'list': self.homeVideoContent().get('list', [])}

    def homeVideoContent(self):
        data = self._post('/App/IndexList/indexList',
                          {'area': '0', 'sub': '5', 'year': '0', 'pageSize': '30',
                           'sort': 'd_id', 'page': 1, 'tid': '1'})
        return {'list': self._videos(data.get('list'))}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid)
        ext = extend or {}
        try:
            page = int(pg)
        except Exception:
            page = 1
        sub = str(ext.get('sub') or DEFAULT_SUB.get(tid, ''))
        data = self._post('/App/IndexList/indexList', {
            'area': str(ext.get('area') or '0'),
            'sub': sub,
            'year': str(ext.get('year') or '0'),
            'pageSize': '30',
            'sort': str(ext.get('sort') or 'd_id'),
            'page': page,
            'tid': tid,
        })
        lst = data.get('list') or []
        total = int(data.get('total') or 0)
        return {'list': self._videos(lst), 'page': page,
                'pagecount': max(1, int(math.ceil(total / 30.0))) if total else page + 1,
                'limit': 30, 'total': total}

    def searchContent(self, key, quick, pg=1):
        data = self._post('/App/Index/findMoreVod', {'keywords': key, 'order_val': '1'}, upper=False)
        return {'list': self._videos(data.get('list')), 'page': 1, 'pagecount': 1}

    # ------------------------------------------------------------ 详情
    def detailContent(self, ids):
        did = str(ids[0]).split('/')[0].split('@')[0]
        info = (self._post('/App/IndexPlay/playInfo',
                           {'token_id': '393668', 'vod_id': did,
                            'mobile_time': str(int(time.time())), 'token': APP_TOKEN},
                           keyname='detail', upper=False) or {}).get('vodInfo') or {}
        vurl = self._post('/App/Resource/Vurl/show',
                          {'vurl_cloud_id': '2', 'vod_d_id': did},
                          keyname='detail', upper=False) or {}
        items = vurl.get('list') or []

        # 按清晰度聚合：同一清晰度 -> 一条线路，内含全部集
        lines = {}
        for it in items:
            title = str(it.get('title') or '').strip() or '正片'
            for res, p in (it.get('play') or {}).items():
                param = (p or {}).get('param') or ''
                m = re.search(r'vurl_id=(\d+)', param)
                if not m:
                    continue
                lines.setdefault(str(res), []).append(
                    '%s$%s/%s?%s' % (title, did, m.group(1), res))

        order = sorted(lines.keys(), key=lambda x: -int(x) if str(x).isdigit() else 0)
        remarks = str(info.get('vod_use_content') or info.get('vod_blurb') or '')
        return {'list': [{
            'vod_id': did,
            'vod_name': info.get('vod_name') or '',
            'vod_pic': info.get('vod_pic') or '',
            'vod_year': str(info.get('vod_year') or ''),
            'vod_area': info.get('vod_area') or '',
            'vod_director': info.get('vod_director') or '',
            'vod_actor': info.get('vod_actor') or '',
            'vod_remarks': ('更新至%s集' % info.get('vod_continu')) if str(info.get('vod_continu') or '0') != '0' else '电影',
            'vod_content': re.sub(r'<[^>]+>', '', remarks),
            'vod_play_from': '$$$'.join(['%sP' % r for r in order]) or '瓜子',
            'vod_play_url': '$$$'.join(['#'.join(lines[r]) for r in order]) or '',
        }]}

    # ------------------------------------------------------------ 播放
    def playerContent(self, flag, id, vipFlags):
        url = ''
        try:
            did, rest = str(id).split('/', 1)
            vurl_id, res = rest.split('?', 1)
            data = self._post('/App/Resource/VurlDetail/showOne', {
                'domain_type': '8', 'vod_id': did, 'type': 'play',
                'resolution': res, 'vurl_id': vurl_id,
            }, keyname='play', upper=False) or {}
            url = data.get('url') or ''
            if not url:
                self.log('瓜子 无直链 state=%s' % data.get('state'))
        except Exception as e:
            self.log('瓜子 播放异常 %s' % e)
        return {'parse': 0, 'playUrl': '', 'url': url,
                'header': {'User-Agent': UA, 'Referer': HOST + '/'}}

    def isVideoFormat(self, url):
        return any(x in (url or '').lower() for x in ('.m3u8', '.mp4', '.flv', '.mkv'))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return [200, 'text/plain', '']
