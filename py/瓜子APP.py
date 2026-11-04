# -*- coding: utf-8 -*-
"""
瓜子影视（py 源，秒播版 v3 协议，2026-11 实测可用）

协议要点：
  1) 设备注册换免费 token：/App/Authentication/Device/signIn（已注册）→ signUp（首次），
     new_key 为本机固定设备号，token 有效期约 30 分钟，过期自动重登
  2) 每次请求随机 16 位 key/iv：
     request_key = AES-128-CBC(body) 的大写 HEX
     keys        = RSA 公钥(PKCS#1 v1.5) 加密 {"iv":...,"key":...} 的 base64
     signature   = md5("token_id=,token=...,phone_type=1,request_key=...,app_id=1,time=...,keys=..."
                       + "*&zvdvdvddbfikkkumtmdwqppp?|4Y!s!2br") 的大写 HEX
  3) 响应 data.response_key 是密文，data.keys 用内置 RSA 私钥解开得 {key, iv}，再 AES 解出 JSON
  4) 播放直链必须带 Referer = playRef（/App/UserInfo/getUserInfo 下发）+ UA Lavf

接口：
     /App/IndexList/indexList         分类列表（area/sub/year/sort/page/pageSize/tid）
     /App/Index/findMoreVod           搜索（keywords/order_val）
     /App/IndexPlay/playInfo          详情（vod_id）
     /App/Resource/Vurl/show          分集+清晰度（vurl_cloud_id=2 / vod_d_id）
     /App/Resource/VurlDetail/showOne 播放直链（domain_type=8/vod_id/type=play/resolution/vurl_id）

每个 vurl 的 play 对象里带 480/720/1080 三档，show_type=2 为不可用档位，
所以按「清晰度」分线路，同一清晰度下按集号排序。

AES / RSA 均为纯 Python 实现，不依赖 pycryptodome，任何 py 内核可直接跑。
"""

import base64
import hashlib
import json
import math
import random
import re
import ssl
import string
import time
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _Spider
except Exception:
    class _Spider(object):
        pass

# ---------------------------------------------------------------- 站点参数
# 2026-11 起改用「秒播」版 App 的 v3 协议（旧 api.8utdtcq.com 只有固定游客 token，
# showOne 对任何片都回同一段 44 秒贴片，已废弃）：
#   1) 设备注册 /App/Authentication/Device/signUp（免费、不要短信）换 token
#   2) 每次请求随机 16 位 key/iv，AES-128-CBC 加密 body -> request_key（大写 HEX）
#      keys = RSA 公钥（PKCS#1 v1.5）加密 {"iv":..,"key":..} 后的 base64
#      signature = md5("token_id=,token=…,phone_type=1,request_key=…,app_id=1,time=…,keys=…"+尾巴) 大写
#   3) 响应 data.keys 用内置 RSA 私钥解开得 {key,iv}，再 AES 解 data.response_key
#   4) 播放地址要带 playRef 作 Referer（/App/UserInfo/getUserInfo 下发）

HOSTS = [
    'https://apinew.uozvr.com',
    'https://sdapi.e2wu4ht.com',
    'https://api.w32z7vtd.com',
    'https://api.6a7nnf7.com',
    'https://api.umygrx3.com',
    'https://api.rmedphk.com',
]
UA = 'okhttp/3.12.0'
PLAY_UA = 'Lavf/57.83.100'
DEVICE_KEY = 'Xk7Qm2Zr9TpW4nJc8VbY'      # 固定设备号：重启后 signIn 能拿回同一个免费账号
OLD_KEY = 'aLFBMWpxBrIDAD1Si/KVvm41'
VER = '3.0.4.8'
VERSION = '2606029'
PKG = 'com.v54f07a912.t4ee50f184.dbb1e7669f20260721'
CODE = 'GZ0313'
SIGN_TAIL = '*&zvdvdvddbfikkkumtmdwqppp?|4Y!s!2br'
DEFAULT_PLAY_REF = 'http://WJiZxLXA2.com/'
PUB_KEY = ('MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDUM5+/y8sPsWkd1/RQS64X259EUwxFXFE5'
           'HlA65MqrxnPs0JqoSRojSDy5QhwvROlaD6TwRQHKMY2OAZ6SnQeUJsChTEFIR9qUkwrs3/MVU'
           'Mxjsv6JS6Oe/juclyJGTgVmDhB55EafXsD0SQYVj/QXXsxR6ewR5E2kL52yAAD4yQIDAQAB')
BODY_KEY = 'MIICdgIBADANBgkqhkiG9w0BAQEFAASCAmAwggJcAgEAAoGAe6hKrWLi1zQmjTT1ozbE4QdFeJGNxubxld6GrFGximxfMsMB6BpJhpcTouAqywAFppiKetUBBbXwYsYU1wNr648XVmPmCMCy4rY8vdliFnbMUj086DU6Z+/oXBdWU3/b1G0DN3E9wULRSwcKZT3wj/cCI1vsCm3gj2R5SqkA9Y0CAwEAAQKBgAJH+4CxV0/zBVcLiBCHvSANm0l7HetybTh/j2p0Y1sTXro4ALwAaCTUeqdBjWiLSo9lNwDHFyq8zX90+gNxa7c5EqcWV9FmlVXr8VhfBzcZo1nXeNdXFT7tQ2yah/odtdcx+vRMSGJd1t/5k5bDd9wAvYdIDblMAg+wiKKZ5KcdAkEA1cCakEN4NexkF5tHPRrR6XOY/XHfkqXxEhMqmNbB9U34saTJnLWIHC8IXys6Qmzz30TtzCjuOqKRRy+FMM4TdwJBAJQZFPjsGC+RqcG5UvVMiMPhnwe/bXEehShK86yJK/g/UiKrO87h3aEu5gcJqBygTq3BBBoH2md3pr/W+hUMWBsCQQChfhTIrdDinKi6lRxrdBnn0Ohjg2cwuqK5zzU9p/N+S9x7Ck8wUI53DKm8jUJE8WAG7WLj/oCOWEh+ic6NIwTdAkEAj0X8nhx6AXsgCYRql1klbqtVmL8+95KZK7PnLWG/IfjQUy3pPGoSaZ7fdquG8bq8oyf5+dzjE/oTXcByS+6XRQJAP/5ciy1bL3NhUhsaOVy55MHXnPjdcTX0FaLi+ybXZIfIQ2P4rb19mVq1feMbCXhz+L1rG8oat5lYKFpe8k83ZA=='


def headers(host, device_id):
    return {
        'User-Agent': UA,
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Ver': VER, 'Version': VERSION, 'api-ver': VER,
        'PackageName': PKG, 'code': CODE, 'deviceId': device_id,
        'lang': 'zh_cn', 'Cache-Control': 'no-cache', 'Referer': host,
    }


def rnd16(n=16):
    pool = string.ascii_uppercase + string.ascii_lowercase + '0123456789'
    return ''.join(random.choice(pool) for _ in range(n))


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


def _rsa_pub(der_b64):
    """SPKI 公钥 -> (n, e)"""
    der = base64.b64decode(der_b64)
    _, outer, _ = _tlv(der, 0)              # SEQUENCE
    _, _, j = _tlv(outer, 0)                # AlgorithmIdentifier
    _, bits, j = _tlv(outer, j)             # BIT STRING
    if bits and bits[0] == 0:
        bits = bits[1:]
    _, seq, _ = _tlv(bits, 0)               # RSAPublicKey
    _, nb, m = _tlv(seq, 0)
    _, eb, m = _tlv(seq, m)
    return int.from_bytes(nb, 'big'), int.from_bytes(eb, 'big')


_PUB = _rsa_pub(PUB_KEY)


def rsa_encrypt_b64(msg):
    """PKCS#1 v1.5 公钥加密"""
    if isinstance(msg, str):
        msg = msg.encode('utf-8')
    n, e = _PUB
    k = (n.bit_length() + 7) // 8
    ps = bytearray()
    while len(ps) < k - 3 - len(msg):
        b = random.randint(1, 255)
        ps.append(b)
    em = b'\x00\x02' + bytes(ps) + b'\x00' + msg
    return base64.b64encode(pow(int.from_bytes(em, 'big'), e, n).to_bytes(k, 'big')).decode()


# ---------------------------------------------------------------- Spider
class Spider(_Spider):
    HOST_NAME = '瓜子影视'

    def getName(self):
        return '瓜子影视'

    # 类级默认值：内核不调 init 时也不会 AttributeError
    _host_idx = 0
    _host = HOSTS[0]
    _device_id = '864150601234'
    _token = ''
    _token_id = ''
    _token_ts = 0
    _play_ref = DEFAULT_PLAY_REF

    def init(self, extend=''):
        self.extend = extend or ''
        self._cache = {}
        self._host_idx = 0
        self._host = HOSTS[0]
        self._device_id = str(864150060000 + random.randint(0, 9999))
        self._token = ''
        self._token_id = ''
        self._token_ts = 0
        self._play_ref = DEFAULT_PLAY_REF
        try:
            self._ensure()
        except Exception:
            pass

    def log(self, msg):
        try:
            print('[瓜子]', msg)
        except Exception:
            pass

    # ------------------------------------------------------------ 网络
    def _http(self, url, body):
        req = urllib.request.Request(url, data=body.encode('utf-8'), method='POST')
        # 直接赋值绕过 urllib 的 header capitalize（服务端按原样校验）
        req.headers = headers(self._host, self._device_id)
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            return r.read().decode('utf-8', 'replace')

    def _sign(self, req_key, t, keys, token):
        raw = ('token_id=,token=%s,phone_type=1,request_key=%s,app_id=1,time=%s,keys=%s%s'
               % (token, req_key, t, keys, SIGN_TAIL))
        return hashlib.md5(raw.encode('utf-8')).hexdigest().upper()

    def _raw(self, path, payload, token='', tries=None):
        """按域名轮询发一次请求，返回解密后的 dict"""
        last = ''
        tries = tries or len(HOSTS)
        for _ in range(tries):
            host = HOSTS[self._host_idx % len(HOSTS)]
            self._host = host
            try:
                k, iv = rnd16(), rnd16()
                body_json = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
                req_key = AES128(k.encode(), iv.encode()).cbc_encrypt(
                    body_json.encode('utf-8')).hex().upper()
                keys = rsa_encrypt_b64(json.dumps({'iv': iv, 'key': k}, separators=(',', ':')))
                t = str(int(time.time()))
                form = {'token_id': '', 'token': token, 'phone_type': '1',
                        'request_key': req_key, 'app_id': '1', 'time': t, 'keys': keys,
                        'phone_model': 'xiaomi-22081212c', 'ad_version': '1'}
                form['signature'] = self._sign(req_key, t, keys, token)
                txt = self._http(host + path, urllib.parse.urlencode(form))
                js = json.loads(txt)
                if 'code' in js and str(js.get('code')) != '200':
                    last = 'code=%s %s' % (js.get('code'), str(js.get('msg'))[:60])
                    self._host_idx += 1
                    continue
                data = js.get('data') or {}
                if not data.get('response_key'):
                    return data
                kv = json.loads(rsa_decrypt_b64(data.get('keys') or '').decode('utf-8'))
                return json.loads(AES128(kv['key'].encode(), kv['iv'].encode())
                                  .cbc_decrypt(bytes.fromhex(data['response_key']))
                                  .decode('utf-8', 'replace'))
            except Exception as e:
                last = '%s: %s' % (type(e).__name__, str(e)[:60])
                self._host_idx += 1
                time.sleep(0.4)
        if last:
            self.log('瓜子 %s 失败 %s' % (path, last))
        return {}

    def _ensure(self):
        """设备注册/登录，拿免费 token（30 分钟有效）"""
        if self._token and time.time() - self._token_ts < 1500:
            return self._token
        # 先 signIn（设备号固定，通常已注册）；失败再 signUp 注册
        for name, payload in (
                ('signIn', {'new_key': DEVICE_KEY, 'old_key': OLD_KEY}),
                ('signUp', {'new_key': DEVICE_KEY, 'old_key': OLD_KEY,
                            'phone_type': 1, 'code': ''})):
            d = self._raw('/App/Authentication/Device/%s' % name, payload, '')
            tok = str(d.get('token') or '')
            if tok:
                self._token = tok
                self._token_id = str(d.get('app_user_id') or '')
                self._token_ts = time.time()
                return tok
        self.log('瓜子 设备登录失败')
        return ''

    def _post(self, path, payload):
        self._ensure()
        d = self._raw(path, payload, self._token)
        if not d:
            self._token = ''
            self._ensure()
            d = self._raw(path, payload, self._token)
        return d or {}

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
        data = self._post('/App/Index/findMoreVod',
                          {'keywords': key, 'ns': '', 'nt': str(int(time.time())),
                           'order_val': '1'})
        return {'list': self._videos(data.get('list')), 'page': 1, 'pagecount': 1}

    # ------------------------------------------------------------ 详情
    def detailContent(self, ids):
        did = str(ids[0]).split('/')[0].split('@')[0]
        self._ensure()
        info = (self._post('/App/IndexPlay/playInfo',
                           {'token_id': self._token_id, 'vod_id': did,
                            'mobile_time': str(int(time.time())),
                            'token': self._token}) or {}).get('vodInfo') or {}
        vurl = self._post('/App/Resource/Vurl/show',
                          {'vurl_cloud_id': '2', 'vod_d_id': did}) or {}
        items = vurl.get('list') or []

        # 按清晰度聚合：同一清晰度 -> 一条线路，内含全部集
        lines = {}
        for it in items:
            title = str(it.get('title') or '').strip() or '正片'
            for res, p in (it.get('play') or {}).items():
                p = p or {}
                if str(p.get('show_type') or '') == '2':   # 该档位不可用（需会员/下架）
                    continue
                param = str(p.get('param') or '')
                m = re.search(r'vurl_id=(\d+)', param)
                if not m:
                    continue
                lines.setdefault(str(res), []).append(
                    '%s$%s|%s|%s' % (title, m.group(1), res, did))

        order = sorted(lines.keys(), key=lambda x: -int(x) if str(x).isdigit() else 0)
        remarks = str(info.get('vod_use_content') or info.get('vod_blurb') or '')
        tag = ''
        first = (items[0].get('pay_type') if items else '') or ''
        if str(first) == '1':
            tag = '·VIP' if str(items[0].get('pay_unlocked') or '0') != '1' else ''
        base_remark = ('更新至%s集' % info.get('vod_continu')) if str(info.get('vod_continu') or '0') != '0' else '电影'
        return {'list': [{
            'vod_id': did,
            'vod_name': info.get('vod_name') or '',
            'vod_pic': info.get('vod_pic') or '',
            'vod_year': str(info.get('vod_year') or ''),
            'vod_area': info.get('vod_area') or '',
            'vod_director': info.get('vod_director') or '',
            'vod_actor': info.get('vod_actor') or '',
            'vod_remarks': base_remark + tag,
            'vod_content': re.sub(r'<[^>]+>', '', remarks),
            'vod_play_from': '$$$'.join(['%sP' % r for r in order]) or '瓜子',
            'vod_play_url': '$$$'.join(['#'.join(lines[r]) for r in order]) or '',
        }]}

    # ------------------------------------------------------------ 播放
    def _get_play_ref(self):
        """播放直链要带 playRef 作 Referer，否则 403"""
        if self._play_ref and self._play_ref != DEFAULT_PLAY_REF:
            return self._play_ref
        try:
            d = self._post('/App/UserInfo/getUserInfo', {})
            ref = str(d.get('playRef') or '')
            if ref.startswith('http'):
                self._play_ref = ref
        except Exception:
            pass
        return self._play_ref or DEFAULT_PLAY_REF

    def playerContent(self, flag, id, vipFlags):
        url = ''
        try:
            parts = str(id).split('|')
            vurl_id = parts[0]
            res = parts[1] if len(parts) > 1 else '1080'
            did = parts[2] if len(parts) > 2 else ''
            self._ensure()
            d = self._post('/App/Resource/VurlDetail/showOne', {
                'vod_id': did, 'vurl_id': vurl_id, 'domain_type': '8',
                'resolution': res, 'type': 'play',
                '_client_ts': str(int(time.time() * 1e9)),
                'mobile_time': str(int(time.time())),
            }) or {}
            url = str(d.get('url') or '')
            if not url:
                self.log('瓜子 无直链 state=%s vip=%s' % (d.get('state'), d.get('vip')))
        except Exception as e:
            self.log('瓜子 播放异常 %s' % e)
        return {'parse': 0, 'playUrl': '', 'url': url,
                'header': {'User-Agent': PLAY_UA, 'Referer': self._get_play_ref()}}

    def isVideoFormat(self, url):
        return any(x in (url or '').lower() for x in ('.m3u8', '.mp4', '.flv', '.mkv'))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return [200, 'text/plain', '']
