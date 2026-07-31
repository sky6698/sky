#coding=utf-8
#!/usr/bin/python
import sys, json, re, time, hashlib, random
sys.path.append('..') 
from base.spider import Spider
import urllib
import urllib.request

class Spider(Spider):
    def getName(self):
        return "中央电视台"

    def init(self,extend=""):
        print("============{0}============".format(extend))
        pass
    def destroy(self): pass
    def isVideoFormat(self,url): pass
    def manualVideoCheck(self): pass

    # ===== 高清 UA 池（模拟真实浏览器）=====
    UA_LIST = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    ]

    def _rand_ua(self):
        return random.choice(self.UA_LIST)

    def _read(self, url, retries=3, timeout=12):
        """带重试的读取，解决'有时失败'"""
        last_err = ""
        for i in range(retries):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": self._rand_ua(),
                    "Referer": "https://tv.cctv.com/",
                    "Origin": "https://tv.cctv.com",
                    "Accept": "*/*",
                })
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return r.read().decode('utf-8', errors='replace')
            except Exception as e:
                last_err = str(e)
                time.sleep(0.5 * (i + 1))
        raise RuntimeError(last_err)

    def _head_ok(self, url, timeout=8):
        """HEAD 探测是否 200"""
        try:
            req = urllib.request.Request(url, method='HEAD', headers={
                "User-Agent": self._rand_ua(),
                "Referer": "https://tv.cctv.com/",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.getcode() == 200
        except:
            return False

    # ===== 核心：获取最高清播放地址 =====
    def get_m3u8(self, urlTxt):
        """
        优先级：
        1) manifest.hls_enc2_url 域名替换为 qcloudcdn → 2000/4000.m3u8
        2) video.chapters4 (2000k/720p) mp4 直链
        3) video.chapters3 (1200k) mp4 直链
        4) 原 hls_url 兜底
        """
        api = "https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do?pid={0}".format(urlTxt)
        try:
            html = self._read(api, retries=3)
            jo = json.loads(html)
        except Exception as e:
            print("[CCTV] API 失败: {0}".format(e))
            return ""

        # ---- 策略 1：enc2 通道 + 域名替换（吾爱破解有效方案）----
        m = jo.get("manifest", {})
        enc2 = m.get("hls_enc2_url", "").strip()
        if enc2:
            # 替换域名为 qcloudcdn（2025-08 验证有效）
            enc2_new = re.sub(r'https?://[^/]+', 'https://dhls2.cntv.qcloudcdn.com', enc2, count=1)
            # 去掉 maxbr 限制，让 CDN 给最高
            enc2_new = re.sub(r'maxbr=\d+&?', '', enc2_new).rstrip('?&')
            # 尝试 4000 → 2000
            for br in ("4000", "2000"):
                cand = re.sub(r'/main/', '/{0}/'.format(br), enc2_new)
                cand = re.sub(r'/main\.m3u8', '/{0}.m3u8'.format(br), cand)
                if self._head_ok(cand):
                    print("[CCTV] enc2/{0} 命中: {1}".format(br, cand[:80]))
                    return cand

        # ---- 策略 2/3：chapters4/chapters3 mp4 直链（不走 HLS，不降级）----
        vid = jo.get("video", {})
        for key in ("chapters4", "chapters3"):
            chap = vid.get(key)
            if isinstance(chap, list):
                for item in chap:
                    u = (item.get("url") or "").strip()
                    if u and (u.endswith(".mp4") or u.endswith(".flv")):
                        print("[CCTV] {0} 直链: {1}".format(key, u[:80]))
                        return u

        # ---- 策略 4：原 hls_url 兜底 ----
        hls = (jo.get("hls_url") or "").strip()
        if hls:
            nobr = re.sub(r'maxbr=\d+&?', '', hls).rstrip('?&')
            if self._head_ok(nobr):
                return nobr
            return hls
        return ""

    # ===== playerContent 改造 =====
    def playerContent(self, flag, id, vipFlags):
        result = {}
        headers = {
            "User-Agent": self._rand_ua(),
            "Referer": "https://tv.cctv.com/",
            "Origin": "https://tv.cctv.com",
        }
        url = ''
        parse = 0
        if flag == 'CCTV':
            url = self.get_m3u8(id)
        else:
            try:
                html = self._read(id, retries=2)
                guid = self.get_RegexGetText(Text=html, RegexText=r'var\s+guid\s*=\s*"(.+?)"', Index=1)
                if guid:
                    url = self.get_m3u8(guid)
                else:
                    url = id
                    parse = 1
            except:
                url = id
                parse = 1

        if not url or url.find('https:') < 0:
            url = id
            parse = 1

        result["parse"] = parse
        result["playUrl"] = ''
        result["url"] = url
        result["header"] = headers
        return result

    # ===== 其余原方法保持不变（webReadFile / get_RegexGetText 等）=====
    def webReadFile(self, urlStr, header):
        return self._read(urlStr)

    def TestWebPage(self, urlStr, email=None):
        return 200 if self._head_ok(urlStr) else 0

    def get_RegexGetText(self, Text, RegexText, Index):
        m = re.search(RegexText, Text, re.M|re.S)
        return m.group(Index) if m else ""

    # ... homeContent / categoryContent / detailContent / searchContent 等保持原样 ...
    # （因篇幅省略，原文件中这些方法无需修改，直接保留即可）

    header = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Host": "tv.cctv.com",
        "Referer": "https://tv.cctv.com/"
    }
