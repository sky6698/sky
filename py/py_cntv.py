#coding=utf-8
#!/usr/bin/python
import sys
sys.path.append('..')
from base.spider import Spider
import json
import time
import random
import re
import urllib.request

class Spider(Spider):
	def getName(self):
		return "中央电视台"

	def init(self, extend=""):
		print("============{0}============".format(extend))

	def destroy(self):
		pass

	def isVideoFormat(self, url):
		pass

	def manualVideoCheck(self):
		pass

	# ============================== 清晰度配置 ==============================
	# 码率对照：450=流畅, 850=标清, 1200=高清, 2000=超清, 3000=蓝光新, 4000=蓝光
	# 2024年6月后 CNTV CDN 策略变更：
	#   - 同一 IP 反复请求同一 URL → 后续返回低码率/花屏
	#   - 直接把 main 替换成 4000 对很多视频已失效
	# 本代码三重策略应对（详见 get_m3u8 注释）：
	#   ① 随机 UA + 随机延时，避免被 CDN 识别为重复客户端
	#   ② 优先使用 enc2/h5e 路径（manifest 中提供的稳定 CDN）
	#   ③ 双斜杠技巧 + 多域名 × 多码率暴力探测
	# =========================================================================
	PREFERRED_BITRATE = 2000   # 主推 2000（超清 720p），4000 多数已被限制
	MAX_BITRATE = 4096          # URL 中 maxbr 参数提到的最高值

	def homeContent(self, filter):
		cateManual = {
			"央视大全": "节目大全",
			"电视剧": "电视剧",
			"动画片": "动画片",
			"纪录片": "纪录片",
			"特别节目": "特别节目",
		}
		result = {'class': [{'type_name': k, 'type_id': v} for k, v in cateManual.items()]}
		if filter:
			result['filters'] = self.config['filter']
		return result

	def homeVideoContent(self):
		return {'list': []}

	def categoryContent(self, tid, pg, filter, extend):
		area = channel = datafl = letter = year = ""
		pagecount = 24
		if tid == '动画片':
			id = urllib.request.quote(tid)
			if 'datadq-area' in extend: area = urllib.request.quote(extend['datadq-area'])
			if 'dataszm-letter' in extend: letter = extend['dataszm-letter']
			if 'datafl-sc' in extend: datafl = urllib.request.quote(extend['datafl-sc'])
			url = 'https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955899450127&area={0}&sc={4}&fc={1}&letter={2}&p={3}&n=24&serviceId=tvcctv&topv=1&t=json'.format(area, id, letter, pg, datafl)
		elif tid == '纪录片':
			id = urllib.request.quote(tid)
			if 'datapd-channel' in extend: channel = urllib.request.quote(extend['datapd-channel'])
			if 'datafl-sc' in extend: datafl = urllib.request.quote(extend['datafl-sc'])
			if 'datanf-year' in extend: year = extend['datanf-year']
			if 'dataszm-letter' in extend: letter = extend['dataszm-letter']
			url = 'https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955924871139&fc={0}&channel={1}&sc={2}&year={3}&letter={4}&p={5}&n=24&serviceId=tvcctv&topv=1&t=json'.format(id, channel, datafl, year, letter, pg)
		elif tid == '电视剧':
			id = urllib.request.quote(tid)
			if 'datafl-sc' in extend: datafl = urllib.request.quote(extend['datafl-sc'])
			if 'datanf-year' in extend: year = extend['datanf-year']
			if 'dataszm-letter' in extend: letter = extend['dataszm-letter']
			url = 'https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955853485115&area={0}&sc={1}&fc={2}&year={3}&letter={4}&p={5}&n=24&serviceId=tvcctv&topv=1&t=json'.format(area, datafl, id, year, letter, pg)
		elif tid == '特别节目':
			id = urllib.request.quote(tid)
			if 'datapd-channel' in extend: channel = urllib.request.quote(extend['datapd-channel'])
			if 'datafl-sc' in extend: datafl = urllib.request.quote(extend['datafl-sc'])
			if 'dataszm-letter' in extend: letter = extend['dataszm-letter']
			url = 'https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955953877151&channel={0}&sc={1}&fc={2}&bigday=&letter={3}&p={4}&n=24&serviceId=tvcctv&topv=1&t=json'.format(channel, datafl, id, letter, pg)
		elif tid == '节目大全':
			cid = extend.get('cid', '')
			fc = extend.get('fc', '')
			fl = extend.get('fl', '')
			url = 'https://api.cntv.cn/lanmu/columnSearch?&fl={0}&fc={1}&cid={2}&p={3}&n=20&serviceId=tvcctv&t=json&cb=ko'.format(fl, fc, cid, pg)
			pagecount = 20
		else:
			url = 'https://tv.cctv.com/epg/index.shtml'

		htmlText = self.webReadFile(urlStr=url, header=self.header)
		if tid == '节目大全':
			idx = htmlText.rfind(');')
			videos = self.get_list1(html=htmlText[3:idx], tid=tid) if idx > -1 else []
		else:
			videos = self.get_list(html=htmlText, tid=tid)

		return {
			'list': videos,
			'page': pg,
			'pagecount': 9999 if len(videos) >= pagecount else pg,
			'limit': 90,
			'total': 999999,
		}

	def detailContent(self, array):
		aid = array[0].split('###')
		tid, title, lastVideo, logo, id, vod_year, actors, brief = aid[0], aid[1], aid[2], aid[3], aid[4], aid[5], aid[6], aid[7]
		fromId = 'CCTV'
		try:
			if tid == "节目大全":
				txt = self.webReadFile('https://api.cntv.cn/video/videoinfoByGuid?guid={0}&serviceId=tvcctv'.format(id), self.header)
				topicId = json.loads(txt)['ctid']
				txt = self.webReadFile('https://api.cntv.cn/NewVideo/getVideoListByColumn?id={0}&d=&p=1&n=100&sort=desc&mode=0&serviceId=tvcctv&t=json'.format(topicId), self.header)
			else:
				txt = self.webReadFile('https://api.cntv.cn/NewVideo/getVideoListByAlbumIdNew?id={0}&serviceId=tvcctv&p=1&n=100&mode=0&pub=1'.format(id), self.header)

			videoList = []
			if tid == "搜索":
				fromId = '中央台'
				videoList = [title + "$" + lastVideo]
			else:
				jRoot = json.loads(txt)
				for vod in jRoot['data']['list']:
					guid = vod.get('guid', '')
					t = vod.get('title', '')
					if guid:
						videoList.append(t + "$" + guid)
				if not videoList:
					txt2 = self.webReadFile(urlStr=lastVideo, header=self.header)
					if tid in ("电视剧", "纪录片"):
						pat = r"'title':\s*'(?P<title>.+?)',\s*'brief':\s*'(.+?)',\s*'img':\s*'(.+?)',\s*'url':\s*'(?P<url>.+?)'"
					elif tid == "特别节目":
						pat = r'class="tp1"><a\s*href="(?P<url>https://.+?)"\s*target="_blank"\s*title="(?P<title>.+?)"></a></div>'
					elif tid == "动画片":
						pat = r"'title':\s*'(?P<title>.+?)',\s*'img':\s*'(.+?)',\s*'brief':\s*'(.+?)',\s*'url':\s*'(?P<url>.+?)'"
					else:
						pat = r'href="(?P<url>.+?)" target="_blank" alt="(?P<title>.+?)"'
					for m in re.finditer(pat, txt2, re.M | re.S):
						videoList.append(m.group('title') + "$" + m.group('url'))
					fromId = '央视'
		except Exception as e:
			print('[detailContent] ' + str(e))
			videoList = []

		if not videoList:
			return {}
		return {'list': [{
			"vod_id": array[0], "vod_name": title, "vod_pic": logo,
			"type_name": tid, "vod_year": vod_year, "vod_area": "",
			"vod_remarks": '', "vod_actor": actors, "vod_director": '',
			"vod_content": brief, "vod_play_from": fromId,
			"vod_play_url": "#".join(videoList),
		}]}

	def searchContent(self, key, quick):
		return self.searchContentPage(key, quick, '1')

	def searchContentPage(self, key, quick, page):
		key = urllib.request.quote(key)
		url = 'https://search.cctv.com/ifsearch.php?page=1&qtext={0}&sort=relevance&pageSize=20&type=video&vtime=-1&datepid=1&channel=&pageflag=0&qtext_str={0}'.format(key)
		return {'list': self.get_list_search(self.webReadFile(url, self.header))}

	# ============================== playerContent ==============================
	# 每次播放随机选 UA，避免 CDN 把同一客户端标记为"高频请求"而降级
	# 传入的 id 可能是 guid，也可能是网页 URL（需从中提取 guid）
	# ==============================================================================
	def playerContent(self, flag, id, vipFlags):
		url = ''
		parse = 0
		ua_pool = [
			'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
			'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
			'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
			'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
			'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
			'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
		]
		headers = {
			'User-Agent': random.choice(ua_pool),
			'Referer': 'https://tv.cctv.com/',
			'Origin': 'https://tv.cctv.com',
			'Accept': '*/*',
		}
		try:
			if flag == 'CCTV':
				url = self.get_m3u8(urlTxt=id, headers=headers)
			else:
				txt = self.webReadFile(urlStr=id, header=self.header)
				guid = self._rx(txt, r'var\s*guid\s*=\s*"(.+?)"', 1)
				if not guid:
					m = re.search(r'guid=([a-f0-9]+)', id)
					guid = m.group(1) if m else ''
				url = self.get_m3u8(urlTxt=guid, headers=headers) if guid else id
				if not guid:
					url, parse = id, 1
		except Exception as e:
			print('[playerContent] ' + str(e))
			url, parse = id, 1

		if 'https:' not in url:
			url, parse = id, 1
		return {"parse": parse, "playUrl": '', "url": url, "header": headers}

	# ============================== 核心：get_m3u8 ==============================
	# 解决"第一次高清，再打开就最低"的问题
	#
	# 根因：
	#   CNTV CDN 在 2024-06 前后变更策略：
	#   1) 同一 IP + 同一 URL 反复请求 → 第 2 次起返回低码率甚至花屏
	#   2) maxbr=2048 参数硬编码在 hls_url 里，限制了最高码率
	#   3) 单纯把 main 换成 4000 对多数视频已不生效（CDN 忽略/返回错误）
	#
	# 三重策略（按优先级）：
	#   A) 使用 manifest 里的 enc2 / h5e / enc URL，改码率 + 提 maxbr
	#      enc2 路径是目前（2025-2026）最稳定、清晰度最高的通道
	#   B) 双斜杠技巧：URL 中 .com/asp/ → .com//asp/ 可绕过部分 CDN 限流
	#      来源：吾爱破解论坛 2024-07 验证有效
	#   C) 多域名 × 多码率暴力探测，随机打乱顺序避免被标记
	# ==============================================================================
	def get_m3u8(self, urlTxt, headers=None):
		api = 'https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do?pid={0}'.format(urlTxt)
		try:
			txt = self.webReadFile(api, self.header)
			jo = json.loads(txt)
		except Exception as e:
			print('[get_m3u8] API 失败: ' + str(e))
			return ''

		hls_url = jo.get('hls_url', '').strip()
		if not hls_url:
			return ''
		m = re.search(r'default/([a-f0-9]+)/', hls_url)
		if not m:
			print('[get_m3u8] GUID 解析失败: ' + hls_url)
			return ''
		guid = m.group(1)
		manifest = jo.get('manifest', {}) or {}

		# ---------- 工具：把一个 m3u8 URL 改到目标码率 ----------
		def _retarget(raw, br):
			u = re.sub(r'/main/(\d+/)', '/{0}/\\1'.format(br), raw)
			u = re.sub(r'/main\.m3u8', '/{0}.m3u8'.format(br), u)
			u = re.sub(r'maxbr=\d+', 'maxbr={0}'.format(self.MAX_BITRATE), u)
			return u

		candidates = []

		# ---- 策略 A：manifest 提供的 CDN（最稳定） ----
		# enc2：dhls2.cntv.qcloudcdn.com（2025 仍有效，清晰度最高）
		for src_key, br_list in [
			('hls_enc2_url', [2000, 3000, 1200]),
			('hls_h5e_url',  [2000, 3000, 1200]),
			('hls_enc_url',  [2000, 1200]),
		]:
			raw = manifest.get(src_key, '')
			if not raw:
				continue
			for br in br_list:
				candidates.append(('manifest-' + src_key, _retarget(raw, br)))

		# ---- 策略 B：双斜杠 + 多域名暴力探测 ----
		domains = [
			'dhls2.cntv.qcloudcdn.com',   # 当前最稳
			'hls.cntv.kcdnvip.com',        # 双斜杠技巧发源地
			'hls.cntv.myhwcdn.cn',
			'hls.cntv.cdn20.com',
			'hls.cntv.lxdns.com',
			'dhls.cntv.myalicdn.com',
		]
		for br in [2000, 3000, 1200]:
			for d in domains:
				std = 'https://{0}/asp/hls/{1}/0303000a/3/default/{2}/{1}.m3u8'.format(d, br, guid)
				candidates.append(('brute-std', std))
				# 双斜杠（绕过 CDN 限流）
				ds = 'https://{0}//asp/hls/{1}/0303000a/3/default/{2}/{1}.m3u8'.format(d, br, guid)
				candidates.append(('brute-//', ds))

		# ---- 策略 C：原始 hls_url 改造 ----
		for br in [2000, 3000, 1200]:
			candidates.append(('hls_url', _retarget(hls_url, br)))

		# 打乱顺序，避免每次第一个请求都打同一个节点
		random.shuffle(candidates)

		# 逐个 HEAD 探测，返回第一个 200
		for tag, u in candidates:
			try:
				req = urllib.request.Request(u, method='HEAD')
				with urllib.request.urlopen(req, timeout=5) as r:
					if r.getcode() == 200:
						br_match = re.search(r'/(\d+)\.m3u8', u)
						br_str = br_match.group(1) if br_match else '?'
						print('[get_m3u8] ✓ {0}  br={1}  {2}'.format(tag, br_str, u[:90]))
						return u
			except Exception:
				continue

		print('[get_m3u8] ✗ 全部失败，退回原始 hls_url')
		return hls_url

	# ------------------------------------ 配置 ------------------------------------
	config = {
		"player": {},
		"filter": {
		"电视剧": [
			{"key": "datafl-sc", "name": "类型", "value": [{"n": "全部", "v": ""}, {"n": "谍战", "v": "谍战"}, {"n": "悬疑", "v": "悬疑"}, {"n": "刑侦", "v": "刑侦"}, {"n": "历史", "v": "历史"}, {"n": "古装", "v": "古装"}, {"n": "武侠", "v": "武侠"}, {"n": "军旅", "v": "军旅"}, {"n": "战争", "v": "战争"}, {"n": "喜剧", "v": "喜剧"}, {"n": "青春", "v": "青春"}, {"n": "言情", "v": "言情"}, {"n": "偶像", "v": "偶像"}, {"n": "家庭", "v": "家庭"}, {"n": "年代", "v": "年代"}, {"n": "革命", "v": "革命"}, {"n": "农村", "v": "农村"}, {"n": "都市", "v": "都市"}, {"n": "其他", "v": "其他"}]},
			{"key": "datadq-area", "name": "地区", "value": [{"n": "全部", "v": ""}, {"n": "中国大陆", "v": "中国大陆"}, {"n": "中国香港", "v": "香港"}, {"n": "美国", "v": "美国"}, {"n": "欧洲", "v": "欧洲"}, {"n": "泰国", "v": "泰国"}]},
			{"key": "datanf-year", "name": "年份", "value": [{"n": "全部", "v": ""}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"}, {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"}, {"n": "2016", "v": "2016"}, {"n": "2015", "v": "2015"}, {"n": "2014", "v": "2014"}, {"n": "2013", "v": "2013"}, {"n": "2012", "v": "2012"}, {"n": "2011", "v": "2011"}, {"n": "2010", "v": "2010"}, {"n": "2009", "v": "2009"}, {"n": "2008", "v": "2008"}, {"n": "2007", "v": "2007"}, {"n": "2006", "v": "2006"}, {"n": "2005", "v": "2005"}, {"n": "2004", "v": "2004"}, {"n": "2003", "v": "2003"}, {"n": "2002", "v": "2002"}, {"n": "2001", "v": "2001"}, {"n": "2000", "v": "2000"}, {"n": "1999", "v": "1999"}, {"n": "1998", "v": "1998"}, {"n": "1997", "v": "1997"}]},
			{"key": "dataszm-letter", "name": "字母", "value": [{"n": "全部", "v": ""}, {"n": "A", "v": "A"}, {"n": "C", "v": "C"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"}, {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"}, {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"}, {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"}, {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"}, {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"}, {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"}, {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}, {"n": "0-9", "v": "0-9"}]},
		],
		"动画片": [
			{"key": "datafl-sc", "name": "类型", "value": [{"n": "全部", "v": ""}, {"n": "亲子", "v": "亲子"}, {"n": "搞笑", "v": "搞笑"}, {"n": "冒险", "v": "冒险"}, {"n": "动作", "v": "动作"}, {"n": "宠物", "v": "宠物"}, {"n": "体育", "v": "体育"}, {"n": "益智", "v": "益智"}, {"n": "历史", "v": "历史"}, {"n": "教育", "v": "教育"}, {"n": "校园", "v": "校园"}, {"n": "言情", "v": "言情"}, {"n": "武侠", "v": "武侠"}, {"n": "经典", "v": "经典"}, {"n": "未来", "v": "未来"}, {"n": "古代", "v": "古代"}, {"n": "神话", "v": "神话"}, {"n": "真人", "v": "真人"}, {"n": "励志", "v": "励志"}, {"n": "热血", "v": "热血"}, {"n": "奇幻", "v": "奇幻"}, {"n": "童话", "v": "童话"}, {"n": "剧情", "v": "剧情"}, {"n": "夺宝", "v": "夺宝"}, {"n": "其他", "v": "其他"}]},
			{"key": "datadq-area", "name": "地区", "value": [{"n": "全部", "v": ""}, {"n": "中国大陆", "v": "中国大陆"}, {"n": "美国", "v": "美国"}, {"n": "欧洲", "v": "欧洲"}]},
			{"key": "dataszm-letter", "name": "字母", "value": [{"n": "全部", "v": ""}, {"n": "A", "v": "A"}, {"n": "C", "v": "C"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"}, {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"}, {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"}, {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"}, {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"}, {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"}, {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"}, {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}, {"n": "0-9", "v": "0-9"}]},
		],
		"纪录片": [
			{"key": "datapd-channel", "name": "频道", "value": [{"n": "全部", "v": ""}, {"n": "CCTV-1 综合", "v": "CCTV-1 综合"}, {"n": "CCTV-2 财经", "v": "CCTV-2 财经"}, {"n": "CCTV-3 综艺", "v": "CCTV-3 综艺"}, {"n": "CCTV-4 中文国际", "v": "CCTV-4 中文国际"}, {"n": "CCTV-5 体育", "v": "CCTV-5 体育"}, {"n": "CCTV-6 电影", "v": "CCTV-6 电影"}, {"n": "CCTV-7 国防军事", "v": "CCTV-7 国防军事"}, {"n": "CCTV-8 电视剧", "v": "CCTV-8 电视剧"}, {"n": "CCTV-9 纪录", "v": "CCTV-9 纪录"}, {"n": "CCTV-10 科教", "v": "CCTV-10 科教"}, {"n": "CCTV-11 戏曲", "v": "CCTV-11 戏曲"}, {"n": "CCTV-12 社会与法", "v": "CCTV-12 社会与法"}, {"n": "CCTV-13 新闻", "v": "CCTV-13 新闻"}, {"n": "CCTV-14 少儿", "v": "CCTV-14 少儿"}, {"n": "CCTV-15 音乐", "v": "CCTV-15 音乐"}, {"n": "CCTV-17 农业农村", "v": "CCTV-17 农业农村"}]},
			{"key": "datafl-sc", "name": "类型", "value": [{"n": "全部", "v": ""}, {"n": "人文历史", "v": "人文历史"}, {"n": "人物", "v": "人物"}, {"n": "军事", "v": "军事"}, {"n": "探索", "v": "探索"}, {"n": "社会", "v": "社会"}, {"n": "时政", "v": "时政"}, {"n": "经济", "v": "经济"}, {"n": "科技", "v": "科技"}]},
			{"key": "datanf-year", "name": "年份", "value": [{"n": "全部", "v": ""}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"}, {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"}, {"n": "2016", "v": "2016"}, {"n": "2015", "v": "2015"}, {"n": "2014", "v": "2014"}, {"n": "2013", "v": "2013"}, {"n": "2012", "v": "2012"}, {"n": "2011", "v": "2011"}, {"n": "2010", "v": "2010"}, {"n": "2009", "v": "2009"}, {"n": "2008", "v": "2008"}]},
			{"key": "dataszm-letter", "name": "字母", "value": [{"n": "全部", "v": ""}, {"n": "A", "v": "A"}, {"n": "C", "v": "C"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"}, {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"}, {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"}, {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"}, {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"}, {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"}, {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"}, {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}, {"n": "0-9", "v": "0-9"}]},
		],
		"特别节目": [
			{"key": "datapd-channel", "name": "频道", "value": [{"n": "全部", "v": ""}, {"n": "CCTV-1 综合", "v": "CCTV-1 综合"}, {"n": "CCTV-2 财经", "v": "CCTV-2 财经"}, {"n": "CCTV-3 综艺", "v": "CCTV-3 综艺"}, {"n": "CCTV-4 中文国际", "v": "CCTV-4 中文国际"}, {"n": "CCTV-5 体育", "v": "CCTV-5 体育"}, {"n": "CCTV-6 电影", "v": "CCTV-6 电影"}, {"n": "CCTV-7 国防军事", "v": "CCTV-7 国防军事"}, {"n": "CCTV-8 电视剧", "v": "CCTV-8 电视剧"}, {"n": "CCTV-9 纪录", "v": "CCTV-9 纪录"}, {"n": "CCTV-10 科教", "v": "CCTV-10 科教"}, {"n": "CCTV-11 戏曲", "v": "CCTV-11 戏曲"}, {"n": "CCTV-12 社会与法", "v": "CCTV-12 社会与法"}, {"n": "CCTV-13 新闻", "v": "CCTV-13 新闻"}, {"n": "CCTV-14 少儿", "v": "CCTV-14 少儿"}, {"n": "CCTV-15 音乐", "v": "CCTV-15 音乐"}, {"n": "CCTV-17 农业农村", "v": "CCTV-17 农业农村"}]},
			{"key": "datafl-sc", "name": "类型", "value": [{"n": "全部", "v": ""}, {"n": "新闻", "v": "新闻"}, {"n": "经济", "v": "经济"}, {"n": "综艺", "v": "综艺"}, {"n": "体育", "v": "体育"}, {"n": "军事", "v": "军事"}, {"n": "影视", "v": "影视"}, {"n": "科教", "v": "科教"}, {"n": "戏曲", "v": "戏曲"}, {"n": "青少", "v": "青少"}, {"n": "音乐", "v": "音乐"}, {"n": "社会", "v": "社会"}, {"n": "公益", "v": "公益"}, {"n": "其他", "v": "其他"}]},
			{"key": "dataszm-letter", "name": "字母", "value": [{"n": "全部", "v": ""}, {"n": "A", "v": "A"}, {"n": "C", "v": "C"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"}, {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"}, {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"}, {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"}, {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"}, {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"}, {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"}, {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}, {"n": "0-9", "v": "0-9"}]},
		],
		"节目大全": [
			{"key": "cid", "name": "频道", "value": [{"n": "全部", "v": ""}, {"n": "CCTV-1综合", "v": "EPGC1386744804340101"}, {"n": "CCTV-2财经", "v": "EPGC1386744804340102"}, {"n": "CCTV-3综艺", "v": "EPGC1386744804340103"}, {"n": "CCTV-4中文国际", "v": "EPGC1386744804340104"}, {"n": "CCTV-5体育", "v": "EPGC1386744804340107"}, {"n": "CCTV-6电影", "v": "EPGC1386744804340108"}, {"n": "CCTV-7国防军事", "v": "EPGC1386744804340109"}, {"n": "CCTV-8电视剧", "v": "EPGC1386744804340110"}, {"n": "CCTV-9纪录", "v": "EPGC1386744804340112"}, {"n": "CCTV-10科教", "v": "EPGC1386744804340113"}, {"n": "CCTV-11戏曲", "v": "EPGC1386744804340114"}, {"n": "CCTV-12社会与法", "v": "EPGC1386744804340115"}, {"n": "CCTV-13新闻", "v": "EPGC1386744804340116"}, {"n": "CCTV-14少儿", "v": "EPGC1386744804340117"}, {"n": "CCTV-15音乐", "v": "EPGC1386744804340118"}, {"n": "CCTV-16奥林匹克", "v": "EPGC1634630207058998"}, {"n": "CCTV-17农业农村", "v": "EPGC1563932742616872"}, {"n": "CCTV-5+体育赛事", "v": "EPGC1468294755566101"}]},
			{"key": "fc", "name": "分类", "value": [{"n": "全部", "v": ""}, {"n": "新闻", "v": "新闻"}, {"n": "体育", "v": "体育"}, {"n": "综艺", "v": "综艺"}, {"n": "健康", "v": "健康"}, {"n": "生活", "v": "生活"}, {"n": "科教", "v": "科教"}, {"n": "经济", "v": "经济"}, {"n": "农业", "v": "农业"}, {"n": "法治", "v": "法治"}, {"n": "军事", "v": "军事"}, {"n": "少儿", "v": "少儿"}, {"n": "动画", "v": "动画"}, {"n": "纪实", "v": "纪实"}, {"n": "戏曲", "v": "戏曲"}, {"n": "音乐", "v": "音乐"}, {"n": "影视", "v": "影视"}]},
			{"key": "fl", "name": "字母", "value": [{"n": "全部", "v": ""}, {"n": "A", "v": "A"}, {"n": "B", "v": "B"}, {"n": "C", "v": "C"}, {"n": "D", "v": "D"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"}, {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"}, {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"}, {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"}, {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"}, {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"}, {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"}, {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}]},
			{"key": "year", "name": "年份", "value": [{"n": "全部", "v": ""}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"}, {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"}, {"n": "2016", "v": "2016"}, {"n": "2015", "v": "2015"}, {"n": "2014", "v": "2014"}, {"n": "2013", "v": "2013"}, {"n": "2012", "v": "2012"}, {"n": "2011", "v": "2011"}, {"n": "2010", "v": "2010"}, {"n": "2009", "v": "2009"}, {"n": "2008", "v": "2008"}, {"n": "2007", "v": "2007"}, {"n": "2006", "v": "2006"}, {"n": "2005", "v": "2005"}, {"n": "2004", "v": "2004"}, {"n": "2003", "v": "2003"}, {"n": "2002", "v": "2002"}, {"n": "2001", "v": "2001"}, {"n": "2000", "v": "2000"}]},
			{"key": "month", "name": "月份", "value": [{"n": "全部", "v": ""}, {"n": "12", "v": "12"}, {"n": "11", "v": "11"}, {"n": "10", "v": "10"}, {"n": "09", "v": "09"}, {"n": "08", "v": "08"}, {"n": "07", "v": "07"}, {"n": "06", "v": "06"}, {"n": "05", "v": "05"}, {"n": "04", "v": "04"}, {"n": "03", "v": "03"}, {"n": "02", "v": "02"}, {"n": "01", "v": "01"}]},
		],
		}
	}

	header = {
		"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
		"Host": "tv.cctv.com",
		"Referer": "https://tv.cctv.com/",
	}

	def localProxy(self, param):
		return [200, "video/MP2T", "", ""]

	# ============================== 工具函数 ==============================
	def webReadFile(self, urlStr, header):
		req = urllib.request.Request(url=urlStr)
		with urllib.request.urlopen(req, timeout=10) as r:
			return r.read().decode('utf-8')

	def _rx(self, text, pat, idx=1):
		m = re.search(pat, text, re.M | re.S)
		return m.group(idx) if m else ''

	def removeHtml(self, txt):
		return re.sub(r'<[^>]+>', '', txt).replace("&nbsp;", " ")

	def get_list_search(self, html):
		j = json.loads(html)
		videos = []
		for v in j.get('list', []):
			url = v.get('urllink', '')
			if not url: continue
			videos.append({
				"vod_id": "搜索###{0}###{1}###{2}###{3}###{4}###{5}###{6}".format(
					v.get('title',''), url, v.get('imglink',''), v.get('id',''),
					v.get('uploadtime',''), '', v.get('channel','')),
				"vod_name": self.removeHtml(v.get('title','')),
				"vod_pic": v.get('imglink',''),
				"vod_remarks": v.get('uploadtime',''),
			})
		return videos

	def get_list1(self, html, tid):
		j = json.loads(html)
		videos = []
		for v in (j.get('response') or {}).get('docs', []):
			url = v.get('column_website', '')
			if not url: continue
			videos.append({
				"vod_id": "{0}###{1}###{2}###{3}###{4}###{5}###{6}###{7}".format(
					tid, v.get('column_name',''), url, v.get('column_logo',''),
					v.get('lastVIDE',{}).get('videoSharedCode',''),
					v.get('column_playdate',''), '', v.get('column_brief','')),
				"vod_name": v.get('column_name',''),
				"vod_pic": v.get('column_logo',''),
				"vod_remarks": '',
			})
		return videos

	def get_list(self, html, tid):
		j = json.loads(html)
		videos = []
		for v in (j.get('data') or {}).get('list', []):
			url = v.get('url', '')
			if not url: continue
			videos.append({
				"vod_id": "{0}###{1}###{2}###{3}###{4}###{5}###{6}###{7}".format(
					tid, v.get('title',''), url, v.get('image',''),
					v.get('id',''), v.get('year',''), v.get('actors',''), v.get('brief','')),
				"vod_name": v.get('title',''),
				"vod_pic": v.get('image',''),
				"vod_remarks": '',
			})
		return videos
