# -*- coding: utf-8 -*-
# 适配站点: https://www.qinav.com
# 分类：动态解析分类页面，一级分类 + 二级筛选下拉（模仿蜜桃）
# 播放：AES-CBC 解密播放 ID，请求 play.php 获取 m3u8
import sys
import re
import json
import base64
import requests
import urllib3
import time
import random
from urllib.parse import unquote, quote, urljoin

urllib3.disable_warnings()
sys.path.append('..')
from base.spider import Spider as BaseSpider

# ===== 纯 Python AES-128 解密模块（与之前相同） =====
_sbox = bytes([
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16])
_inv_sbox = bytes([
    0x52,0x09,0x6a,0xd5,0x30,0x36,0xa5,0x38,0xbf,0x40,0xa3,0x9e,0x81,0xf3,0xd7,0xfb,
    0x7c,0xe3,0x39,0x82,0x9b,0x2f,0xff,0x87,0x34,0x8e,0x43,0x44,0xc4,0xde,0xe9,0xcb,
    0x54,0x7b,0x94,0x32,0xa6,0xc2,0x23,0x3d,0xee,0x4c,0x95,0x0b,0x42,0xfa,0xc3,0x4e,
    0x08,0x2e,0xa1,0x66,0x28,0xd9,0x24,0xb2,0x76,0x5b,0xa2,0x49,0x6d,0x8b,0xd1,0x25,
    0x72,0xf8,0xf6,0x64,0x86,0x68,0x98,0x16,0xd4,0xa4,0x5c,0xcc,0x5d,0x65,0xb6,0x92,
    0x6c,0x70,0x48,0x50,0xfd,0xed,0xb9,0xda,0x5e,0x15,0x46,0x57,0xa7,0x8d,0x9d,0x84,
    0x90,0xd8,0xab,0x00,0x8c,0xbc,0xd3,0x0a,0xf7,0xe4,0x58,0x05,0xb8,0xb3,0x45,0x06,
    0xd0,0x2c,0x1e,0x8f,0xca,0x3f,0x0f,0x02,0xc1,0xaf,0xbd,0x03,0x01,0x13,0x8a,0x6b,
    0x3a,0x91,0x11,0x41,0x4f,0x67,0xdc,0xea,0x97,0xf2,0xcf,0xce,0xf0,0xb4,0xe6,0x73,
    0x96,0xac,0x74,0x22,0xe7,0xad,0x35,0x85,0xe2,0xf9,0x37,0xe8,0x1c,0x75,0xdf,0x6e,
    0x47,0xf1,0x1a,0x71,0x1d,0x29,0xc5,0x89,0x6f,0xb7,0x62,0x0e,0xaa,0x18,0xbe,0x1b,
    0xfc,0x56,0x3e,0x4b,0xc6,0xd2,0x79,0x20,0x9a,0xdb,0xc0,0xfe,0x78,0xcd,0x5a,0xf4,
    0x1f,0xdd,0xa8,0x33,0x88,0x07,0xc7,0x31,0xb1,0x12,0x10,0x59,0x27,0x80,0xec,0x5f,
    0x60,0x51,0x7f,0xa9,0x19,0xb5,0x4a,0x0d,0x2d,0xe5,0x7a,0x9f,0x93,0xc9,0x9c,0xef,
    0xa0,0xe0,0x3b,0x4d,0xae,0x2a,0xf5,0xb0,0xc8,0xeb,0xbb,0x3c,0x83,0x53,0x99,0x61,
    0x17,0x2b,0x04,0x7e,0xba,0x77,0xd6,0x26,0xe1,0x69,0x14,0x63,0x55,0x21,0x0c,0x7d])
_rcon = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]
def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff
def _gf_mul(a, b):
    r = 0
    for _ in range(8):
        if b & 1: r ^= a
        a = _xtime(a)
        b >>= 1
    return r
_mul_e = bytes(_gf_mul(0x0e, i) for i in range(256))
_mul_b = bytes(_gf_mul(0x0b, i) for i in range(256))
_mul_d = bytes(_gf_mul(0x0d, i) for i in range(256))
_mul_9 = bytes(_gf_mul(0x09, i) for i in range(256))
_key_schedules = {}
def _key_schedule(key):
    k = bytes(key)
    if k in _key_schedules: return _key_schedules[k]
    w = []
    for i in range(4):
        w.append([key[4*i], key[4*i+1], key[4*i+2], key[4*i+3]])
    for i in range(4, 44):
        temp = w[i-1][:]
        if i % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [_sbox[b] for b in temp]
            temp[0] ^= _rcon[i//4 - 1]
        w.append([w[i-4][j] ^ temp[j] for j in range(4)])
    _key_schedules[k] = w
    return w
def _dec_block(block, w):
    s0,s1,s2,s3,s4,s5,s6,s7,s8,s9,s10,s11,s12,s13,s14,s15 = block
    s0 ^= w[40][0]; s1 ^= w[40][1]; s2 ^= w[40][2]; s3 ^= w[40][3]
    s4 ^= w[41][0]; s5 ^= w[41][1]; s6 ^= w[41][2]; s7 ^= w[41][3]
    s8 ^= w[42][0]; s9 ^= w[42][1]; s10^= w[42][2]; s11^= w[42][3]
    s12^= w[43][0]; s13^= w[43][1]; s14^= w[43][2]; s15^= w[43][3]
    box = _inv_sbox
    for rnd in range(9, 0, -1):
        t0=box[s0]; t1=box[s13]; t2=box[s10]; t3=box[s7]
        t4=box[s4]; t5=box[s1]; t6=box[s14]; t7=box[s11]
        t8=box[s8]; t9=box[s5]; t10=box[s2]; t11=box[s15]
        t12=box[s12]; t13=box[s9]; t14=box[s6]; t15=box[s3]
        rk=w[rnd*4]; t0^=rk[0]; t1^=rk[1]; t2^=rk[2]; t3^=rk[3]
        rk=w[rnd*4+1]; t4^=rk[0]; t5^=rk[1]; t6^=rk[2]; t7^=rk[3]
        rk=w[rnd*4+2]; t8^=rk[0]; t9^=rk[1]; t10^=rk[2]; t11^=rk[3]
        rk=w[rnd*4+3]; t12^=rk[0]; t13^=rk[1]; t14^=rk[2]; t15^=rk[3]
        s0 =_mul_e[t0]^_mul_b[t1]^_mul_d[t2]^_mul_9[t3]
        s1 =_mul_9[t0]^_mul_e[t1]^_mul_b[t2]^_mul_d[t3]
        s2 =_mul_d[t0]^_mul_9[t1]^_mul_e[t2]^_mul_b[t3]
        s3 =_mul_b[t0]^_mul_d[t1]^_mul_9[t2]^_mul_e[t3]
        s4 =_mul_e[t4]^_mul_b[t5]^_mul_d[t6]^_mul_9[t7]
        s5 =_mul_9[t4]^_mul_e[t5]^_mul_b[t6]^_mul_d[t7]
        s6 =_mul_d[t4]^_mul_9[t5]^_mul_e[t6]^_mul_b[t7]
        s7 =_mul_b[t4]^_mul_d[t5]^_mul_9[t6]^_mul_e[t7]
        s8 =_mul_e[t8]^_mul_b[t9]^_mul_d[t10]^_mul_9[t11]
        s9 =_mul_9[t8]^_mul_e[t9]^_mul_b[t10]^_mul_d[t11]
        s10=_mul_d[t8]^_mul_9[t9]^_mul_e[t10]^_mul_b[t11]
        s11=_mul_b[t8]^_mul_d[t9]^_mul_9[t10]^_mul_e[t11]
        s12=_mul_e[t12]^_mul_b[t13]^_mul_d[t14]^_mul_9[t15]
        s13=_mul_9[t12]^_mul_e[t13]^_mul_b[t14]^_mul_d[t15]
        s14=_mul_d[t12]^_mul_9[t13]^_mul_e[t14]^_mul_b[t15]
        s15=_mul_b[t12]^_mul_d[t13]^_mul_9[t14]^_mul_e[t15]
    t0=box[s0]; t1=box[s13]; t2=box[s10]; t3=box[s7]
    t4=box[s4]; t5=box[s1]; t6=box[s14]; t7=box[s11]
    t8=box[s8]; t9=box[s5]; t10=box[s2]; t11=box[s15]
    t12=box[s12]; t13=box[s9]; t14=box[s6]; t15=box[s3]
    rk=w[0]; t0^=rk[0]; t1^=rk[1]; t2^=rk[2]; t3^=rk[3]
    rk=w[1]; t4^=rk[0]; t5^=rk[1]; t6^=rk[2]; t7^=rk[3]
    rk=w[2]; t8^=rk[0]; t9^=rk[1]; t10^=rk[2]; t11^=rk[3]
    rk=w[3]; t12^=rk[0]; t13^=rk[1]; t14^=rk[2]; t15^=rk[3]
    return bytes([t0,t1,t2,t3,t4,t5,t6,t7,t8,t9,t10,t11,t12,t13,t14,t15])
def _aes_cbc_decrypt(data, key, iv):
    if not data or len(data) % 16: return data
    n = len(data) // 16
    w = _key_schedule(key)
    out = bytearray(len(data))
    prev = iv
    for i in range(n):
        block = data[i*16:(i+1)*16]
        dec = _dec_block(block, w)
        for j in range(16):
            out[i*16+j] = dec[j] ^ prev[j]
        prev = block
    pad = out[-1]
    if 1 <= pad <= 16:
        return bytes(out[:-pad])
    return bytes(out)

# ===== Spider =====
class Spider(BaseSpider):
    session = requests.Session()
    host = 'https://www.qinav.com'
    _debug = True

    # 缓存分类数据（避免每次请求）
    _category_cache = None

    def _log(self, msg):
        if self._debug:
            print(f'[qinav] {msg}')

    def getName(self):
        return 'qinav'

    def isVideoFormat(self, url):
        if not url:
            return False
        return '.m3u8' in url or '.mp4' in url or '.ts' in url

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def localProxy(self, param):
        return [404, 'text/plain', '']

    def init(self, extend=''):
        self.session.verify = False
        self.session.headers.update(self._get_headers())
        # 预热获取 cookies
        try:
            self.session.get(self.host, timeout=10)
        except:
            pass

    def _get_headers(self, referer=None):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Referer': referer or self.host + '/',
        }
        return headers

    def _fetch(self, url, referer=None, retries=3):
        for i in range(retries):
            try:
                if referer is None:
                    referer = self.host + '/'
                headers = self._get_headers(referer)
                if i > 0:
                    time.sleep(random.uniform(1.0, 2.5))
                r = self.session.get(url, headers=headers, timeout=30, verify=False, allow_redirects=True)
                r.encoding = 'utf-8'
                if r.status_code == 200:
                    return r.text
                elif r.status_code in [403, 429, 503]:
                    self._log(f'请求被拦截 [{r.status_code}]，重试 {i+1}/{retries}')
                else:
                    self._log(f'状态码 {r.status_code}，可能无内容')
                    return ''
            except Exception as e:
                self._log(f'请求异常 [{e}]，重试 {i+1}/{retries}')
        return ''

    @staticmethod
    def _decode_b64(encoded_str):
        try:
            raw = base64.b64decode(encoded_str)
            return unquote(raw.decode('utf-8'))
        except:
            return encoded_str

    # ==================== 动态解析分类（模仿蜜桃） ====================
    def _fetch_category_data(self):
        """从 /site.html 解析出一级站点和二级子分类"""
        if self._category_cache is not None:
            return self._category_cache

        url = f'{self.host}/site.html'
        html = self._fetch(url)
        if not html:
            self._log('获取分类页面失败，使用硬编码备用')
            return self._get_fallback_categories()

        categories = []
        # 按 h3 和紧随的 div.word 分组
        pattern = r'<h3>(.*?)</h3>\s*<div class="word">(.*?)</div>'
        matches = re.findall(pattern, html, re.S)
        if not matches:
            self._log('未找到分类结构，使用备用')
            return self._get_fallback_categories()

        for site_name, word_html in matches:
            site_name = site_name.strip()
            # 提取所有子分类链接 /site/{sid}/{cid}.html
            sub_links = re.findall(r'<a href="/site/(\d+)/(\d+)\.html">([^<]+)</a>', word_html)
            if not sub_links:
                continue
            # 构建子分类列表
            sub_list = []
            for sid, cid, cname in sub_links:
                cname = cname.strip()
                if not cname or cname == '0':
                    continue
                sub_list.append((sid, cid, cname))
            if sub_list:
                categories.append({
                    'site_name': site_name,
                    'site_id': sub_list[0][0],  # 同一站点的sid相同
                    'subs': [(cid, cname) for _, cid, cname in sub_list]
                })

        if not categories:
            self._log('解析分类失败，使用备用')
            return self._get_fallback_categories()

        self._category_cache = categories
        self._log(f'动态解析到 {len(categories)} 个一级分类')
        return categories

    def _get_fallback_categories(self):
        """硬编码备用（与之前一致）"""
        fallback = [
            {'site_name': '视频1站', 'site_id': '1', 'subs': [
                ('42', '大秀视频'), ('4', '国产精品'), ('27', '自拍偷拍'), ('28', 'AV明星'),
                ('20', '动漫精品'), ('23', '日韩精品'), ('3', '欧美精品'), ('41', '教师学生'),
                ('18', '中文字幕'), ('36', '巨乳系列'), ('32', '3P合辑'), ('16', '人妻系列'),
                ('25', '制服诱惑'), ('2', '强奸乱伦'), ('40', 'SM重味'), ('1', '日韩无码'),
                ('22', '伦理影片')
            ]},
            {'site_name': '视频2站', 'site_id': '2', 'subs': [
                ('3', '日韩无码'), ('4', 'AV明星'), ('34', '童颜巨乳'), ('1', '国产自拍'),
                ('26', '强奸乱伦'), ('2', '欧美极品'), ('35', '高潮喷吹'), ('24', '重咸口味'),
                ('21', '动漫精品'), ('22', '极骚萝莉'), ('20', '中文字幕'), ('37', '绝美少女'),
                ('36', '激情口交')
            ]},
            {'site_name': '视频3站', 'site_id': '3', 'subs': [
                ('74', '少妇人妻'), ('52', '网曝黑料'), ('47', '国产视频'), ('48', '国产传媒'),
                ('67', '明星爆料'), ('71', '日本无码'), ('63', '制服诱惑'), ('82', '精品短视频'),
                ('49', '国产探花'), ('53', '日本有码'), ('61', '偷拍自拍'), ('64', '欧美精品'),
                ('75', '角色扮演'), ('56', '校园春色'), ('54', '主播大秀'), ('68', '三级伦理'),
                ('80', '男同性恋'), ('51', '野战户外'), ('70', '成人动漫'), ('78', '中文字幕'),
                ('57', 'SM虐待'), ('81', '反差系列'), ('72', '重口猎奇'), ('66', 'AV女优'),
                ('59', '巨乳系列'), ('76', '女同性恋'), ('69', 'AV解说'), ('77', '黑人专区'),
                ('73', 'VR视频'), ('62', '强奸乱伦'), ('50', '极品学生')
            ]},
            {'site_name': '视频4站', 'site_id': '4', 'subs': [
                ('2', '亚洲有码'), ('24', '国产自拍'), ('20', '美女主播'), ('49', 'AV解说'),
                ('1', '亚洲无码'), ('3', '欧美情色'), ('5', '动漫卡通')
            ]},
            {'site_name': '视频5站', 'site_id': '5', 'subs': [
                ('2', '国产主播'), ('9', '中文字幕'), ('5', '欧美性爱'), ('4', '无码专区'),
                ('1', '亚洲情色'), ('12', '卡通动画'), ('14', '少女萝莉'), ('3', '国产自拍'),
                ('15', '重口色情'), ('10', '制服诱惑'), ('7', '强奸乱伦'), ('13', '视频伦理'),
                ('8', '巨乳美乳'), ('33', '福利姬'), ('11', '女同性恋'), ('6', '熟女人妻')
            ]},
            {'site_name': '视频6站', 'site_id': '6', 'subs': [
                ('1', '国产情色'), ('20', '中文字幕'), ('23', '欧美情色'), ('31', '精品推荐'),
                ('2', '日本无码'), ('22', '成人动漫'), ('25', '长腿丝袜'), ('21', '网红主播'),
                ('27', '韩国伦理'), ('28', '香港伦理'), ('26', '邻家人妻'), ('3', 'AV明星'),
                ('24', '国模私拍'), ('35', 'AV明星1')
            ]},
            {'site_name': '视频7站', 'site_id': '7', 'subs': [
                ('25', '亚洲有码'), ('27', '巨乳美乳'), ('28', '人妻熟女'), ('51', '女优系列'),
                ('63', '恋腿狂魔'), ('31', '萝莉少女'), ('37', '日本精品'), ('36', '口交颜射'),
                ('35', '制服丝袜'), ('29', '强奸乱伦'), ('53', '风情旗袍'), ('44', '欺辱凌辱'),
                ('32', '伦理三级'), ('39', '素人自拍'), ('47', '91探花'), ('23', '主播直播'),
                ('58', '网曝门'), ('34', '自拍偷拍'), ('38', 'Cosplay'), ('41', '韩国御姐'),
                ('50', '古装扮演'), ('48', '网红流出'), ('46', '多人多P'), ('26', '中文字幕'),
                ('55', '瑜伽裤'), ('49', '野外露出'), ('22', '国产色情'), ('20', '精品推荐'),
                ('33', '成人动漫'), ('30', '欧美精品'), ('52', '可爱学生'), ('54', '兽耳系列'),
                ('40', '台湾辣妹'), ('45', '剧情介绍'), ('24', '亚洲无码'), ('42', '唯美港姐'),
                ('56', '闷骚护士'), ('43', '东南亚AV'), ('60', '女同性恋'), ('61', '男同性恋')
            ]},
            {'site_name': '视频8站', 'site_id': '8', 'subs': [
                ('16', '强奸乱伦'), ('6', '中文字幕'), ('38', '女优明星'), ('36', '网爆黑料'),
                ('3', '制服诱惑'), ('35', '网红头条'), ('40', 'AV解说'), ('5', 'AI换脸'),
                ('7', '卡通动漫'), ('9', '美女主播'), ('10', '国产自拍'), ('33', '抖音视频'),
                ('37', '欧美无码'), ('12', '萝莉少女'), ('1', '无码专区'), ('2', '麻豆传媒'),
                ('8', '欧美系列'), ('14', '多人群交'), ('11', '熟女人妻'), ('15', '美乳巨乳'),
                ('39', 'SM调教'), ('4', '三级伦理'), ('34', '韩国主播'), ('13', '女同性爱')
            ]}
        ]
        # 转换为与动态解析一致的格式
        result = []
        for item in fallback:
            result.append({
                'site_name': item['site_name'],
                'site_id': item['site_id'],
                'subs': item['subs']
            })
        return result

    # ==================== 首页（返回分类 + 推荐视频） ====================
    def homeContent(self, filter):
        try:
            categories = self._fetch_category_data()
            classes = []
            filters = {}
            for cat in categories:
                cid = f'site_{cat["site_id"]}'
                classes.append({'type_id': cid, 'type_name': cat['site_name']})
                # 构建二级筛选下拉
                sub_values = [{'n': '全部', 'v': ''}]
                for sub_id, sub_name in cat['subs']:
                    sub_values.append({'n': sub_name, 'v': f'{cat["site_id"]}_{sub_id}'})
                filters[cid] = [{'key': 'sub', 'name': '分类', 'value': sub_values}]

            # 推荐列表：取第一个站的第一个子分类
            home_list = []
            if categories:
                first_cat = categories[0]
                if first_cat['subs']:
                    first_sub = first_cat['subs'][0]
                    home_list = self._get_video_list(first_cat['site_id'], first_sub[0], 1)

            self._log(f'首页返回 {len(classes)} 个一级分类, 推荐视频 {len(home_list)} 个')
            return {
                'class': classes,
                'filters': filters,
                'type': '影视',
                'list': home_list,
                'page': 1,
                'pagecount': 1,
                'limit': len(home_list),
                'total': len(home_list)
            }
        except Exception as e:
            self._log(f'homeContent 异常: {e}')
            return {'class': [], 'filters': {}, 'type': '影视', 'list': [], 'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0}

    def homeVideoContent(self):
        return {'list': []}

    # ==================== 分类内容 ====================
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if pg else 1
            if isinstance(extend, str):
                try:
                    extend = json.loads(extend)
                except:
                    extend = {}
            if not isinstance(extend, dict):
                extend = {}

            if str(tid).startswith('site_'):
                site_id = str(tid).replace('site_', '')
                sub_val = extend.get('sub', filter.get('sub', '')) if isinstance(filter, dict) else extend.get('sub', '')
                # 如果 sub_val 只有 site_id 没有 cat_id，默认取第一个子分类
                if sub_val and '_' not in str(sub_val):
                    categories = self._fetch_category_data()
                    for cat in categories:
                        if str(cat['site_id']) == str(sub_val) and cat['subs']:
                            sub_val = f"{sub_val}_{cat['subs'][0][0]}"
                            break
                if not sub_val:
                    # 默认取第一个子分类
                    categories = self._fetch_category_data()
                    for cat in categories:
                        if cat['site_id'] == site_id and cat['subs']:
                            sub_val = f"{site_id}_{cat['subs'][0][0]}"
                            break
                if sub_val and '_' in sub_val:
                    sid, catid = sub_val.split('_')
                    self._log(f'加载二级分类: site={sid}, cat={catid}, page={page}')
                    return self._load_sub_videos(sid, catid, page)
                else:
                    return {'list': [], 'page': page, 'pagecount': 1, 'limit': 0, 'total': 0}

            # 兼容旧格式
            if '_' in str(tid) and not str(tid).startswith('site_'):
                parts = str(tid).split('_')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    return self._load_sub_videos(parts[0], parts[1], page)

            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 0, 'total': 0}
        except Exception as e:
            self._log(f'categoryContent 异常: {e}')
            return {'list': [], 'page': int(pg) if pg else 1, 'pagecount': 1, 'limit': 0, 'total': 0}

    def _load_sub_videos(self, site_id, cat_id, page):
        items = self._get_video_list(site_id, cat_id, page)
        total_page = page + 1
        url = f'{self.host}/site/{site_id}/{cat_id}.html'
        html = self._fetch(url)
        if html:
            pages = re.findall(r'[?&]page=(\d+)', html)
            if pages:
                total_page = max(int(p) for p in pages) + 1
        self._log(f'视频列表: site={site_id}, cat={cat_id}, page={page}, 获取到 {len(items)} 条')
        return {
            'list': items,
            'page': page,
            'pagecount': total_page,
            'limit': len(items),
            'total': total_page * len(items)
        }

    # ==================== 视频列表解析（适配 qinav 结构） ====================
    def _parse_list(self, html):
        items = []
        # Pattern: <a title="" href="/video/ID.html"> <li class="image">...</li> <li class="title">标题</li> </a>
        for a in re.finditer(r'<a[^>]+title="[^"]*"\s+href="(/video/(\d+)\.html)"[^>]*>.*?<li class="title">(.*?)</li>', html, re.S):
            vid = a.group(2)
            title = re.sub(r'<[^>]+>', '', a.group(3)).strip()
            # Extract cover from img attribute or data-original
            block = a.group(0)
            img = re.search(r'img="([^"]+)"', block) or re.search(r'data-src="([^"]+)"', block) or re.search(r'src="([^"]+)"', block)
            pic = img.group(1) if img else ''
            title = re.sub(r'\s+', ' ', title).strip()
            items.append({'vod_id': vid, 'vod_name': title, 'vod_pic': pic, 'vod_remarks': ''})
        if items:
            self._log(f'解析到 {len(items)} 个视频')
            return items

    def _get_video_list(self, site_id, cat_id, page):
        urls = [
            f'{self.host}/site/{site_id}/{cat_id}.html',
            f'{self.host}/list/{site_id}_{cat_id}.html',
            f'{self.host}/category/{cat_id}.html?site_id={site_id}',
            f'{self.host}/index.php?c=site&a=index&site_id={site_id}&cat_id={cat_id}',
            f'{self.host}/videolist/{site_id}/{cat_id}.html',
        ]
        for url in urls:
            if page > 1:
                sep = '&' if '?' in url else '?'
                url += f'{sep}page={page}'
            self._log(f'尝试列表URL: {url}')
            html = self._fetch(url)
            if html:
                items = self._parse_list(html)
                if items:
                    return items
        return []

    # ==================== 详情解析 ====================
    def _fetch_detail(self, vid):
        urls = [
            f'{self.host}/video/{vid}.html',
            f'{self.host}/v/{vid}.html',
        ]
        for url in urls:
            self._log(f'获取详情: {url}')
            html = self._fetch(url, referer=self.host)
            if html and ('video' in html or 'play' in html or 'm3u8' in html or 'mp4' in html or 'iframe' in html):
                detail = self._parse_detail(html, vid, url)
                if detail and detail.get('vod_play_url'):
                    return detail
        return None

    def _parse_detail(self, html, vid, base_url):
        title = ''
        m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        if m: title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if not title:
            m = re.search(r'<title>([^<]+)</title>', html)
            if m: title = m.group(1).strip()
        cover = ''
        m = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', html)
        if m: cover = m.group(1)
        if not cover:
            m = re.search(r'<img[^>]+class="[^"]*cover[^"]*"[^>]+src="([^"]+)"', html, re.S)
            if m: cover = m.group(1)
        if not cover:
            m = re.search(r'data-original="([^"]+)"', html)
            if m: cover = m.group(1)

        # 尝试提取加密参数
        hadeedg252 = hcdeedg252 = 0
        aes_key = aes_iv = ''
        m = re.search(r'var\s+hadeedg252\s*=\s*(\d+)', html)
        if m: hadeedg252 = int(m.group(1))
        m = re.search(r'var\s+hcdeedg252\s*=\s*(\d+)', html)
        if m: hcdeedg252 = int(m.group(1))
        m = re.search(r"var\s+argdeqweqweqwe\s*=\s*'([^']+)'", html)
        if m: aes_key = m.group(1)
        m = re.search(r"var\s+hdddedg252\s*=\s*'([^']+)'", html)
        if m: aes_iv = m.group(1)

        if hadeedg252 and aes_key and aes_iv:
            mm = re.search(r"mvarr\['10_1'\]\s*=\s*(\[.*?\]);", html, re.S)
            if mm:
                mvarr_str = mm.group(1)
                items = re.findall(r"\['([^']*)','([^']*)','([^']*)','([^']*)','([^']*)','([^']*)'\]", mvarr_str)
                if items:
                    urls = []
                    for iframe_id, enc, html_part, prefix, empty, label in items:
                        if not enc or not prefix: continue
                        pid = self._decrypt_id(enc, hadeedg252, hcdeedg252, aes_key, aes_iv)
                        if not pid: continue
                        for res, label_name in [('1080', '1080P'), ('720', '720P'), ('480', '480P')]:
                            urls.append(f'{label_name}${vid}|{pid}|{res}')
                    if urls:
                        return {
                            'vod_id': vid,
                            'vod_name': title or vid,
                            'vod_pic': cover or '',
                            'vod_content': '',
                            'vod_play_from': 'qinav',
                            'vod_play_url': '#'.join(urls),
                        }

        # 备用通用解析
        play_urls = []
        seen = set()
        def add(label, url):
            if url in seen: return
            seen.add(url)
            play_urls.append(f'{label}${url}')

        for src in set(re.findall(r'<iframe[^>]+(?:src|data-src)=["\']([^"\']+)["\']', html)):
            full = src if src.startswith('http') else urljoin(base_url, src)
            # 尝试从 embed 页面直接提取 m3u8
            try:
                embed_html = self._fetch(full, referer=self.host)
                if embed_html:
                    m3u8_m = re.search(r'''url\s*=\s*['"](https?://[^'"]+\.m3u8[^'"]*)['"]''', embed_html)
                    if m3u8_m:
                        add('直链', m3u8_m.group(1))
                        continue
                    for vm in re.finditer(r'https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*', embed_html):
                        add('直链', vm.group())
                        break
            except: pass
            add('外链', full)
        for media in set(re.findall(r'https?://[^\s"\'<>]+\.(?:m3u8|mp4|flv|mkv|ts)(?:\?[^\s"\'<>]*)?', html)):
            add('直链', media)
        for media in set(re.findall(r'<(?:video|source)[^>]+src=["\']([^"\']+)["\']', html)):
            if any(ext in media for ext in ['.m3u8', '.mp4', '.flv', '.ts']):
                full = media if media.startswith('http') else urljoin(base_url, media)
                add('HTML5', full)
        for script in re.findall(r'<script[^>]*>(.*?)</script>', html, re.S):
            for m in re.finditer(r'(?:url|src|file)\s*[:=]\s*["\']([^"\']+)["\']', script):
                url = m.group(1)
                if url.startswith('http') and any(ext in url for ext in ['.m3u8', '.mp4', '.flv']):
                    add('JS提取', url)
        if not play_urls:
            site_id = ''
            source_id = ''
            m_sid = re.search(r'site_id[=:](\d+)', html)
            if m_sid: site_id = m_sid.group(1)
            m_src = re.search(r'source_id[=:](\d+)', html)
            if m_src: source_id = m_src.group(1)
            if site_id and source_id:
                add('默认线路', f'{self.host}/play.php?site_id={site_id}&source_id={source_id}')
            else:
                add('默认线路', f'{self.host}/play.php?vid={vid}')
        if not play_urls:
            return None
        sources = []
        urls = []
        for pu in play_urls:
            sn, url = pu.split('$', 1)
            sources.append(sn)
            urls.append(f'{sn}${url}')
        return {
            'vod_id': vid,
            'vod_name': title or vid,
            'vod_pic': cover or '',
            'vod_play_from': '$$$'.join(sources),
            'vod_play_url': '#'.join(urls),
            'vod_content': title or '',
        }

    def _decrypt_id(self, enc, xor_key, base, aes_key, aes_iv):
        try:
            sep = chr(base + 97)
            parts = enc.split(sep)
            s1 = ''.join(chr(int(p, base) ^ xor_key) for p in parts if p)
            data = base64.b64decode(s1)
            plain = _aes_cbc_decrypt(data, aes_key.encode(), aes_iv.encode())
            return plain.decode('utf-8')
        except Exception:
            return ''

    def detailContent(self, ids):
        try:
            vid = str(ids[0] if isinstance(ids, list) else ids)
            detail = self._fetch_detail(vid)
            if not detail: return {'list': []}
            return {'list': [detail]}
        except Exception as e:
            self._log(f'detailContent 异常: {e}')
            return {'list': []}

    # ==================== 播放 ====================
    def playerContent(self, flag, id, vipFlags=None):
        try:
            if id and not id.startswith('http'):
                parts = id.split('|')
                if len(parts) == 3:
                    vid, pid, res = parts
                    url = f'{self.host}/js/player/play.php?numresolution={res}&lo=on&id={pid}'
                    text = self._fetch(url)
                    m3u8 = ''
                    if text:
                        mm = re.search(r'videoSources\s*=\s*(\[.*?\]);', text, re.S)
                        if mm:
                            arr = mm.group(1)
                            sources = re.findall(r"src:\s*'([^']+)'[^}]*?size:\s*(\d+)", arr, re.S)
                            if sources:
                                target = int(res) if res.isdigit() else 0
                                for u, s in sources:
                                    if int(s) == target:
                                        m3u8 = u
                                        break
                                if not m3u8:
                                    m3u8 = sources[0][0]
                        if not m3u8:
                            mm = re.search(r'https?://[^\s"<>\']+?\.m3u8', text)
                            if mm: m3u8 = mm.group(0)
                    return {'parse': 0, 'url': m3u8, 'header': {'Referer': self.host + '/'}, 'position': '0'}
            # 直接 http 链接
            return {'parse': 0, 'url': id, 'header': {'Referer': self.host + '/'}, 'position': '0'}
        except Exception as e:
            self._log(f'playerContent 异常: {e}')
            return {'parse': 0, 'url': '', 'header': {}, 'position': '0'}

    def searchContent(self, key, quick, pg='1'):
        try:
            page = int(pg) if pg else 1
            url = f'{self.host}/search.php?keyword={quote(key)}&page={page}'
            html = self._fetch(url, referer=self.host)
            items = self._parse_list(html) if html else []
            return {'list': items, 'page': page, 'pagecount': page + 1, 'limit': len(items), 'total': page * len(items)}
        except Exception as e:
            self._log(f'searchContent 异常: {e}')
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0}