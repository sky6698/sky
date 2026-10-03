#coding=utf-8
#!/usr/bin/python
import sys
sys.path.append('..') 
from base.spider import Spider
import json
import struct
import time
import base64
import re
from urllib import request, parse
import urllib
import urllib.request
import time

# ==================== 清晰度配置（逐切片实测结论，不是猜的）====================
# 【一句话】
#   央视的 720P 是加密的（DRM），密钥算法在央视自己的 WASM 播放器里，纯 py 源解不了；
#   不加密能拿到的最高画质只有 640x360；另有少数节目额外附带不加密的 720P MP4 分章文件。
#   所以本源：720P 只在「该节目确有明文 MP4 分章」时才出现，且拆成单文件分段播（任何播放器都能放）；
#   其余情况给明文 640x360 / 480x270。全程绝不把加密流喂给播放器 —— 那正是花屏的原因。
#
# 【实测 1：HLS 三条通道逐档比对（取首切片算 md5 + 解 H.264 SPS 量分辨率）】
#              450          850          1200          2000
#   明文通道   480x270 好   640x360 好   480x270 假    480x270 假   （1200/2000 的首切片与 450 字节数完全相同 = 服务端静默降级）
#   enc 通道   480x270      640x360      1280x720 好   1280x720 好  （每帧多一枚非标准 NAL type 24）
#   h5e 通道   480x270      640x360      1280x720 好   1280x720 好  （每帧多一枚非标准 NAL type 25）
#   enc2 通道  403          403          403           403
#   → 明文通道天花板 = 850 = 640x360；它的 master 清单里甚至只列 1 档（480x270），850 要自己拼。
#   → 全站不存在「不加密的 720P HLS」，720P 只出现在 enc/h5e 上。
#
# 【实测 2：加密方式 —— 为什么喂给播放器就是花屏】
#   · 明文流与加密流的切片头、切片长度逐字节一致，只有切片内容不同 → 属于「切片级选择性加密」。
#   · 每帧视频数据里插了一枚非标准 NAL 当标志位：enc 用 type 24、h5e 用 type 25；
#     h5e 那枚 NAL 的载荷首字节 = 0x01，正对应公开解密器里的 "payload[0] === 1 才解密"；
#     enc 的 type 24 里能看到 udrmGetLicense 字样 → 是许可/密钥协商。
#   · 解密靠央视的 WASM 播放器内核（cctv.worker.js，3.18MB，emscripten 产物）+ 服务端下发密钥。
#     开源界（cctv-h5e-decrypt 等）也只能靠在 Node/浏览器里跑那坨 WASM 实现，没有纯算法版本。
#     → py 源做不到，只能绕开。
#   · 其它绕行尝试全部失败：去掉 contentid、换 iPhone/Android UA、跨主机换路径前缀、
#     在明文主机上改清晰度层级目录 —— 清一色 403/404，或者拿到的仍是降级流。
#
# 【实测 3：不加密的 720P 藏在 MP4 分章接口里，但只对部分节目开放】
#   接口 video 字段带 4 组明文 MP4 分章（央视网页播放器默认档就是 chapters3）：
#     chapters  (418000)  480x270   |  chapters2 (818000)  640x360
#     chapters3 (1200000) 1280x720  |  chapters4 (2000000) 1280x720
#   标准明文 MP4（ftyp mp42 + avcC / H.264 High L3.1），免鉴权、不限 UA、支持 Range、响应 0.06s。
#   但 chapters[i].url 是「内容级」开关，不是随机：
#     《新闻联播》10/10 次都有真实 url；
#     电视剧 / 纪录片 / 动画片 / 特别节目 / 焦点访谈 / 百家讲坛 → 0/10 次，url 恒为空串
#     （版权内容只走加密 HLS，自制的新闻类才给明文 MP4）。
#   → 所以 720P 线路必须「有才给、没有就不出现」。
#
# 【实测 4：为什么 720P 要拆成分段，而不是做成一条 HLS】
#   每段自带 ftyp+moov，是「独立完整 MP4」。实测把它当成 HLS 的 segment：
#     · ffmpeg 系（IJKplayer）：只播得出第 1 段，日志报 "Found duplicated MOOV Atom. Skipped it"；
#     · ExoPlayer：官方支持矩阵里 HLS 容器只有 MPEG-TS 与 fMP4/CMAF，非分片 MP4 不在列。
#   → 做成一条 HLS 只会「放 2 分钟就断」。所以本源把每段单列成一条选集（parse=0 直接播单文件 MP4），
#     任何播放器都能放，代价是选集条目变长。
#
# 【站点没有 1080P】HLS 的 3000/4000 实测 404；2000 与 1200 同为 1280x720，只是码率更高。
QUALITY_LEVELS = [
	("超清720P", "chapters4", 2000),   # 明文 MP4 分章，1280x720 / 2.0Mbps（仅部分节目有）
	("高清720P", "chapters3", 1200),   # 明文 MP4 分章，1280x720 / 1.2Mbps（央视自身默认档）
	("标清360P", "plain", 850),        # 明文 HLS，640x360 —— 通用最高画质
	("流畅270P", "plain", 450)         # 明文 HLS，480x270
]
MP4_LEVELS = [(n, s) for n, s, c in QUALITY_LEVELS if s != 'plain']   # 依赖明文 MP4 分章的两条线路
MAX_MP4_EPISODE = 6                      # 铺分段时最多展开多少集：一集 15 段，展开 6 集 ≈ 90 条，
                                         # 再往后就还是按原样列（那些集仍可用 360P/270P 线路看）。
                                         # 展开会让 720P 线路的条目数比 360P 线路多，切线路时选集下标会错位，
                                         # 这是「把独立 MP4 拆成一段一条」的固有代价。
PLAIN_SAFE_QUALITY = ("850", "450")      # 明文通道里真实可用的档位
QUALITY_BITRATE = {"450": 450, "850": 850}
SIZE_RATIO_MIN = 0.55                    # 分片实收体积不得低于该档位理论码率的 55%，用于识别被降级的假高清
UA_STR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.54 Safari/537.36"
REFERER_STR = "https://tv.cctv.com/"
PROXY_TS = "http://127.0.0.1:9978/proxy?do=py&url={0}"   # localProxy 兜底改写清单时用的分片代理前缀
_VINFO_CACHE = {}                        # pid -> (时间戳, 接口结果)，同一集在 detail/player 之间复用，省一次请求
_VINFO_TTL = 90


class Spider(Spider):  # 元类 默认的元类 type
	def getName(self):
		return "中央电视台"#可搜索
	def init(self,extend=""):
		print("============{0}============".format(extend))
		pass
	def destroy(self):
		pass
	def isVideoFormat(self,url):
		pass
	def manualVideoCheck(self):
		pass
	def homeContent(self,filter):
		result = {}
		cateManual = {
			"央视大全":"节目大全",
			"电视剧": "电视剧",
			"动画片": "动画片",
			"纪录片": "纪录片",
			"特别节目": "特别节目"
			
		}
		classes = []
		for k in cateManual:
			classes.append({
				'type_name':k,
				'type_id':cateManual[k]
			})
		result['class'] = classes
		if(filter):
			result['filters'] = self.config['filter']
		return result
	def homeVideoContent(self):
		result = {
			'list':[]
		}
		return result
	def categoryContent(self,tid,pg,filter,extend):
		result = {}
		month = ""#月
		year = ""#年
		area=''#地区
		channel=''#频道
		datafl=''#类型
		letter=''#字母
		pagecount=24
		if tid=='动画片':
			id=urllib.parse.quote(tid)
			if 'datadq-area' in extend.keys():
				area=urllib.parse.quote(extend['datadq-area'])
			if 'dataszm-letter' in extend.keys():
				letter=extend['dataszm-letter']
			if 'datafl-sc' in extend.keys():
				datafl=urllib.parse.quote(extend['datafl-sc'])
			url='https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955899450127&area={0}&sc={4}&fc={1}&letter={2}&p={3}&n=24&serviceId=tvcctv&topv=1&t=json'.format(area,id,letter,pg,datafl)
		elif tid=='纪录片':
			id=urllib.parse.quote(tid)
			if 'datapd-channel' in extend.keys():
				channel=urllib.parse.quote(extend['datapd-channel'])
			if 'datafl-sc' in extend.keys():
				datafl=urllib.parse.quote(extend['datafl-sc'])
			if 'datanf-year' in extend.keys():
				year=extend['datanf-year']
			if 'dataszm-letter' in extend.keys():
				letter=extend['dataszm-letter']
			url='https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955924871139&fc={0}&channel={1}&sc={2}&year={3}&letter={4}&p={5}&n=24&serviceId=tvcctv&topv=1&t=json'.format(id,channel,datafl,year,letter,pg)
		elif tid=='电视剧':
			id=urllib.parse.quote(tid)
			if 'datafl-sc' in extend.keys():
				datafl=urllib.parse.quote(extend['datafl-sc'])
			if 'datanf-year' in extend.keys():
				year=extend['datanf-year']
			if 'dataszm-letter' in extend.keys():
				letter=extend['dataszm-letter']
			url='https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955853485115&area={0}&sc={1}&fc={2}&year={3}&letter={4}&p={5}&n=24&serviceId=tvcctv&topv=1&t=json'.format(area,datafl,id,year,letter,pg)
		elif tid=='特别节目':
			id=urllib.parse.quote(tid)
			if 'datapd-channel' in extend.keys():
				channel=urllib.parse.quote(extend['datapd-channel'])
			if 'datafl-sc' in extend.keys():
				datafl=urllib.parse.quote(extend['datafl-sc'])
			if 'dataszm-letter' in extend.keys():
				letter=extend['dataszm-letter']
			url='https://api.cntv.cn/list/getVideoAlbumList?channelid=CHAL1460955953877151&channel={0}&sc={1}&fc={2}&bigday=&letter={3}&p={4}&n=24&serviceId=tvcctv&topv=1&t=json'.format(channel,datafl,id,letter,pg)
		elif tid=='节目大全':
			cid=''#频道
			if 'cid' in extend.keys():
				cid=extend['cid']
			fc=''#分类
			if 'fc' in extend.keys():
				fc=extend['fc']
			fl=''#字母
			if 'fl' in extend.keys():
				fl=extend['fl']
			url = 'https://api.cntv.cn/lanmu/columnSearch?&fl={0}&fc={1}&cid={2}&p={3}&n=20&serviceId=tvcctv&t=json&cb=ko'.format(fl,fc,cid,pg)
			pagecount=20
		else:
			url = 'https://tv.cctv.com/epg/index.shtml'

		videos=[]
		htmlText =self.webReadFile(urlStr=url,header=self.header)
		if tid=='节目大全':
			index=htmlText.rfind(');')
			if index>-1:
				htmlText=htmlText[3:index]
				videos =self.get_list1(html=htmlText,tid=tid)
		else:
			videos =self.get_list(html=htmlText,tid=tid)
		#print(videos)
		
		result['list'] = videos
		result['page'] = pg
		result['pagecount'] = 9999 if len(videos)>=pagecount else pg
		result['limit'] = 90
		result['total'] = 999999
		return result
	def detailContent(self,array):
		result={}
		#参数兼容：ids 可能是字符串/列表/元组，也可能是空
		if isinstance(array,(list,tuple)):
			if len(array)==0:
				return {}
			array=[str(array[0])]
		elif array is None:
			return {}
		else:
			array=[str(array)]
		aid = array[0].split('###')
		while len(aid) < 8:
			aid.append('')
		tid = aid[0]
		logo = aid[3]
		lastVideo = aid[2]
		title = aid[1]
		id= aid[4]
		
		vod_year= aid[5]
		actors= aid[6]
		brief= aid[7]
		fromId='CCTV'
		if tid=="节目大全":
			lastUrl = 'https://api.cntv.cn/video/videoinfoByGuid?guid={0}&serviceId=tvcctv'.format(id)
			htmlTxt = self.webReadFile(urlStr=lastUrl,header=self.header)
			topicId=json.loads(htmlTxt)['ctid']
			Url = "https://api.cntv.cn/NewVideo/getVideoListByColumn?id={0}&d=&p=1&n=100&sort=desc&mode=0&serviceId=tvcctv&t=json".format(topicId)
			htmlTxt = self.webReadFile(urlStr=Url,header=self.header)
		else:
			Url='https://api.cntv.cn/NewVideo/getVideoListByAlbumIdNew?id={0}&serviceId=tvcctv&p=1&n=100&mode=0&pub=1'.format(id)
		jRoot = ''
		videoList = []
		try:
			if tid=="搜索":
				fromId='中央台'
				videoList=[title+"$"+lastVideo]
			else:
				htmlTxt=self.webReadFile(urlStr=Url,header=self.header)
				jRoot = json.loads(htmlTxt)
				data=jRoot['data']
				jsonList=data['list']
				videoList=self.get_EpisodesList(jsonList=jsonList)
				if len(videoList)<1:
					htmlTxt=self.webReadFile(urlStr=lastVideo,header=self.header)
					if tid=="电视剧" or tid=="纪录片":
						patternTxt=r"'title':\s*'(?P<title>.+?)',\n{0,1}\s*'brief':\s*'(.+?)',\n{0,1}\s*'img':\s*'(.+?)',\n{0,1}\s*'url':\s*'(?P<url>.+?)'"
					elif tid=="特别节目":
						patternTxt=r'class="tp1"><a\s*href="(?P<url>https://.+?)"\s*target="_blank"\s*title="(?P<title>.+?)"></a></div>'
					elif tid=="动画片":
						patternTxt=r"'title':\s*'(?P<title>.+?)',\n{0,1}\s*'img':\s*'(.+?)',\n{0,1}\s*'brief':\s*'(.+?)',\n{0,1}\s*'url':\s*'(?P<url>.+?)'"
					elif tid=="节目大全":
						patternTxt=r'href="(?P<url>.+?)" target="_blank" alt="(?P<title>.+?)" title=".+?">'
					videoList=self.get_EpisodesList_re(htmlTxt=htmlTxt,patternTxt=patternTxt)
					fromId='央视'
		except:
			pass
		if len(videoList) == 0:
			return {}
		vod = {
			"vod_id":array[0],
			"vod_name":title,
			"vod_pic":logo,
			"type_name":tid,
			"vod_year":vod_year,
			"vod_area":"",
			"vod_remarks":'',
			"vod_actor":actors,
			"vod_director":'',
			"vod_content":brief
		}
		# ---- 线路组装 ----
		#   标清360P / 流畅270P：同一条选集，播放时走不同的明文档位，任何节目都有
		#   超清720P / 高清720P：只有该节目确有「明文 MP4 分章」时才出现，
		#     并把分章铺成一条条选集（每段就是 CDN 上一个独立完整的 MP4，parse=0 直出）
		episodes = "#".join(videoList)
		lines = []
		lines.extend(self.buildMp4Lines(videoList))
		lines.append(("标清360P", episodes))
		lines.append(("流畅270P", episodes))
		vod['vod_play_from'] = "$$$".join([n for n, _ in lines])
		vod['vod_play_url'] = "$$$".join([e for _, e in lines])
		result = {
			'list':[
				vod
			]
		}
		return result
	def get_lineList(self,Txt,mark,after):
		circuit=[]
		origin=Txt.find(mark)
		while origin>8:
			end=Txt.find(after,origin)
			circuit.append(Txt[origin:end])
			origin=Txt.find(mark,end)
		return circuit	
	def get_RegexGetTextLine(self,Text,RegexText,Index):
		returnTxt=[]
		pattern = re.compile(RegexText, re.M|re.S)
		ListRe=pattern.findall(Text)
		if len(ListRe)<1:
			return returnTxt
		for value in ListRe:
			returnTxt.append(value)	
		return returnTxt
	def searchContent(self,key,quick,pg='1'):
		return self.searchContentPage(key, quick, pg)
	def searchContentPage(self, key, quick, page):
		key=urllib.parse.quote(key)
		Url='https://search.cctv.com/ifsearch.php?page=1&qtext={0}&sort=relevance&pageSize=20&type=video&vtime=-1&datepid=1&channel=&pageflag=0&qtext_str={0}'.format(key)
		htmlTxt=self.webReadFile(urlStr=Url,header=self.header)
		videos=self.get_list_search(html=htmlTxt,tid='搜索')
		result = {
			'list':videos
		}
		return result
	def playerContent(self,flag,id,vipFlags):
		result = {}
		url=''
		parse=0
		headers = {
			'User-Agent':UA_STR,
			'Referer':REFERER_STR
		}
		# flag 是清晰度线路名；兼容旧线路名（CCTV/央视/中央台）时回落到最低档，保证一定有画面
		quality = str(flag) if flag is not None else ''
		src = ''
		for name, s, code in QUALITY_LEVELS:
			if name == quality:
				src = s
		if len(src) == 0:
			quality = QUALITY_LEVELS[-1][0]
			src = QUALITY_LEVELS[-1][1]
		#参数兼容：id 可能是字符串/列表/元组
		if isinstance(id,(list,tuple)):
			id = str(id[0]) if len(id)>0 else ''
		elif id is None:
			id = ''
		else:
			id = str(id)
		try:
			if self.isMediaUrl(id):
				# 720P 线路的选集条目本身就是 CDN 上的单文件 MP4，直接播，不用再解析
				url = id
			else:
				if str(id).find('http')==0:
					# 视频页地址：先取页面里的真实 pid
					html=self.webReadFile(urlStr=id,header=self.header)
					pid=self.get_RegexGetText(Text=html,RegexText=r'var\sguid\s*=\s*"([^"]+)"',Index=1)
				else:
					pid=id
				if len(pid)>0:
					if src=='plain':
						# 明文 HLS 普通通道（标清360P / 流畅270P）
						url=self.get_m3u8(urlTxt=pid,quality=quality)
					else:
						# 720P 兜底：正常情况 detailContent 已经确认过「这一集确有分章」才列出该线路；
						# 万一这一刻接口变了，就退回明文最高档 —— 绝不去碰 enc/h5e 加密流
						url=self.get_m3u8(urlTxt=pid,quality='标清360P')
		except :
			url=''
		if url.find('http')!=0:
			url=id
			parse=1
		result["parse"] = parse#1=嗅探,0=播放
		result["playUrl"] = ''
		result["url"] = url
		result["header"] =headers
		return result
	config = {
		"player": {},
		"filter": {
		"电视剧":[
		{"key":"datafl-sc","name":"类型","value":[{"n":"全部","v":""},{"n":"谍战","v":"谍战"},{"n":"悬疑","v":"悬疑"},{"n":"刑侦","v":"刑侦"},{"n":"历史","v":"历史"},{"n":"古装","v":"古装"},{"n":"武侠","v":"武侠"},{"n":"军旅","v":"军旅"},{"n":"战争","v":"战争"},{"n":"喜剧","v":"喜剧"},{"n":"青春","v":"青春"},{"n":"言情","v":"言情"},{"n":"偶像","v":"偶像"},{"n":"家庭","v":"家庭"},{"n":"年代","v":"年代"},{"n":"革命","v":"革命"},{"n":"农村","v":"农村"},{"n":"都市","v":"都市"},{"n":"其他","v":"其他"}]},
		{"key":"datadq-area","name":"地区","value":[{"n":"全部","v":""},{"n":"中国大陆","v":"中国大陆"},{"n":"中国香港","v":"香港"},{"n":"美国","v":"美国"},{"n":"欧洲","v":"欧洲"},{"n":"泰国","v":"泰国"}]},
		{"key":"datanf-year","name":"年份","value":[{"n":"全部","v":""},{"n":"2023","v":"2023"},{"n":"2022","v":"2022"},{"n":"2021","v":"2021"},{"n":"2020","v":"2020"},{"n":"2019","v":"2019"},{"n":"2018","v":"2018"},{"n":"2017","v":"2017"},{"n":"2016","v":"2016"},{"n":"2015","v":"2015"},{"n":"2014","v":"2014"},{"n":"2013","v":"2013"},{"n":"2012","v":"2012"},{"n":"2011","v":"2011"},{"n":"2010","v":"2010"},{"n":"2009","v":"2009"},{"n":"2008","v":"2008"},{"n":"2007","v":"2007"},{"n":"2006","v":"2006"},{"n":"2005","v":"2005"},{"n":"2004","v":"2004"},{"n":"2003","v":"2003"},{"n":"2002","v":"2002"},{"n":"2001","v":"2001"},{"n":"2000","v":"2000"},{"n":"1999","v":"1999"},{"n":"1998","v":"1998"},{"n":"1997","v":"1997"}]},
		{"key":"dataszm-letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"C","v":"C"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0-9"}]}
		],
		"动画片":[
		{"key":"datafl-sc","name":"类型","value":[{"n":"全部","v":""},{"n":"亲子","v":"亲子"},{"n":"搞笑","v":"搞笑"},{"n":"冒险","v":"冒险"},{"n":"动作","v":"动作"},{"n":"宠物","v":"宠物"},{"n":"体育","v":"体育"},{"n":"益智","v":"益智"},{"n":"历史","v":"历史"},{"n":"教育","v":"教育"},{"n":"校园","v":"校园"},{"n":"言情","v":"言情"},{"n":"武侠","v":"武侠"},{"n":"经典","v":"经典"},{"n":"未来","v":"未来"},{"n":"古代","v":"古代"},{"n":"神话","v":"神话"},{"n":"真人","v":"真人"},{"n":"励志","v":"励志"},{"n":"热血","v":"热血"},{"n":"奇幻","v":"奇幻"},{"n":"童话","v":"童话"},{"n":"剧情","v":"剧情"},{"n":"夺宝","v":"夺宝"},{"n":"其他","v":"其他"}]},
		{"key":"datadq-area","name":"地区","value":[{"n":"全部","v":""},{"n":"中国大陆","v":"中国大陆"},{"n":"美国","v":"美国"},{"n":"欧洲","v":"欧洲"}]},
		{"key":"dataszm-letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"C","v":"C"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0-9"}]}
		],
		"纪录片":[
		{"key":"datapd-channel","name":"频道","value":[{"n":"全部","v":""},{"n":"CCTV{1 综合","v":"CCTV{1 综合"},{"n":"CCTV{2 财经","v":"CCTV{2 财经"},{"n":"CCTV{3 综艺","v":"CCTV{3 综艺"},{"n":"CCTV{4 中文国际","v":"CCTV{4 中文国际"},{"n":"CCTV{5 体育","v":"CCTV{5 体育"},{"n":"CCTV{6 电影","v":"CCTV{6 电影"},{"n":"CCTV{7 国防军事","v":"CCTV{7 国防军事"},{"n":"CCTV{8 电视剧","v":"CCTV{8 电视剧"},{"n":"CCTV{9 纪录","v":"CCTV{9 纪录"},{"n":"CCTV{10 科教","v":"CCTV{10 科教"},{"n":"CCTV{11 戏曲","v":"CCTV{11 戏曲"},{"n":"CCTV{12 社会与法","v":"CCTV{12 社会与法"},{"n":"CCTV{13 新闻","v":"CCTV{13 新闻"},{"n":"CCTV{14 少儿","v":"CCTV{14 少儿"},{"n":"CCTV{15 音乐","v":"CCTV{15 音乐"},{"n":"CCTV{17 农业农村","v":"CCTV{17 农业农村"}]},
		{"key":"datafl-sc","name":"类型","value":[{"n":"全部","v":""},{"n":"人文历史","v":"人文历史"},{"n":"人物","v":"人物"},{"n":"军事","v":"军事"},{"n":"探索","v":"探索"},{"n":"社会","v":"社会"},{"n":"时政","v":"时政"},{"n":"经济","v":"经济"},{"n":"科技","v":"科技"}]},
		{"key":"datanf-year","name":"年份","value":[{"n":"全部","v":""},{"n":"2023","v":"2023"},{"n":"2022","v":"2022"},{"n":"2021","v":"2021"},{"n":"2020","v":"2020"},{"n":"2019","v":"2019"},{"n":"2018","v":"2018"},{"n":"2017","v":"2017"},{"n":"2016","v":"2016"},{"n":"2015","v":"2015"},{"n":"2014","v":"2014"},{"n":"2013","v":"2013"},{"n":"2012","v":"2012"},{"n":"2011","v":"2011"},{"n":"2010","v":"2010"},{"n":"2009","v":"2009"},{"n":"2008","v":"2008"}]},
		{"key":"dataszm-letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"C","v":"C"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0-9"}]}
		],
		"特别节目":[
		{"key":"datapd-channel","name":"频道","value":[{"n":"全部","v":""},{"n":"CCTV{1 综合","v":"CCTV{1 综合"},{"n":"CCTV{2 财经","v":"CCTV{2 财经"},{"n":"CCTV{3 综艺","v":"CCTV{3 综艺"},{"n":"CCTV{4 中文国际","v":"CCTV{4 中文国际"},{"n":"CCTV{5 体育","v":"CCTV{5 体育"},{"n":"CCTV{6 电影","v":"CCTV{6 电影"},{"n":"CCTV{7 国防军事","v":"CCTV{7 国防军事"},{"n":"CCTV{8 电视剧","v":"CCTV{8 电视剧"},{"n":"CCTV{9 纪录","v":"CCTV{9 纪录"},{"n":"CCTV{10 科教","v":"CCTV{10 科教"},{"n":"CCTV{11 戏曲","v":"CCTV{11 戏曲"},{"n":"CCTV{12 社会与法","v":"CCTV{12 社会与法"},{"n":"CCTV{13 新闻","v":"CCTV{13 新闻"},{"n":"CCTV{14 少儿","v":"CCTV{14 少儿"},{"n":"CCTV{15 音乐","v":"CCTV{15 音乐"},{"n":"CCTV{17 农业农村","v":"CCTV{17 农业农村"}]},
		{"key":"datafl-sc","name":"类型","value":[{"n":"全部","v":""},{"n":"全部","v":"全部"},{"n":"新闻","v":"新闻"},{"n":"经济","v":"经济"},{"n":"综艺","v":"综艺"},{"n":"体育","v":"体育"},{"n":"军事","v":"军事"},{"n":"影视","v":"影视"},{"n":"科教","v":"科教"},{"n":"戏曲","v":"戏曲"},{"n":"青少","v":"青少"},{"n":"音乐","v":"音乐"},{"n":"社会","v":"社会"},{"n":"公益","v":"公益"},{"n":"其他","v":"其他"}]},
		{"key":"dataszm-letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"C","v":"C"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0-9"}]}
		],
		"节目大全":[{"key":"cid","name":"频道","value":[{"n":"全部","v":""},{"n":"CCTV-1综合","v":"EPGC1386744804340101"},{"n":"CCTV-2财经","v":"EPGC1386744804340102"},{"n":"CCTV-3综艺","v":"EPGC1386744804340103"},{"n":"CCTV-4中文国际","v":"EPGC1386744804340104"},{"n":"CCTV-5体育","v":"EPGC1386744804340107"},{"n":"CCTV-6电影","v":"EPGC1386744804340108"},{"n":"CCTV-7国防军事","v":"EPGC1386744804340109"},{"n":"CCTV-8电视剧","v":"EPGC1386744804340110"},{"n":"CCTV-9纪录","v":"EPGC1386744804340112"},{"n":"CCTV-10科教","v":"EPGC1386744804340113"},{"n":"CCTV-11戏曲","v":"EPGC1386744804340114"},{"n":"CCTV-12社会与法","v":"EPGC1386744804340115"},{"n":"CCTV-13新闻","v":"EPGC1386744804340116"},{"n":"CCTV-14少儿","v":"EPGC1386744804340117"},{"n":"CCTV-15音乐","v":"EPGC1386744804340118"},{"n":"CCTV-16奥林匹克","v":"EPGC1634630207058998"},{"n":"CCTV-17农业农村","v":"EPGC1563932742616872"},{"n":"CCTV-5+体育赛事","v":"EPGC1468294755566101"}]},{"key":"fc","name":"分类","value":[{"n":"全部","v":""},{"n":"新闻","v":"新闻"},{"n":"体育","v":"体育"},{"n":"综艺","v":"综艺"},{"n":"健康","v":"健康"},{"n":"生活","v":"生活"},{"n":"科教","v":"科教"},{"n":"经济","v":"经济"},{"n":"农业","v":"农业"},{"n":"法治","v":"法治"},{"n":"军事","v":"军事"},{"n":"少儿","v":"少儿"},{"n":"动画","v":"动画"},{"n":"纪实","v":"纪实"},{"n":"戏曲","v":"戏曲"},{"n":"音乐","v":"音乐"},{"n":"影视","v":"影视"}]},{"key":"fl","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"B","v":"B"},{"n":"C","v":"C"},{"n":"D","v":"D"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"}]},{"key":"year","name":"年份","value":[{"n":"全部","v":""},{"n":"2023","v":"2023"},{"n":"2022","v":"2022"},{"n":"2021","v":"2021"},{"n":"2020","v":"2020"},{"n":"2019","v":"2019"},{"n":"2018","v":"2018"},{"n":"2017","v":"2017"},{"n":"2016","v":"2016"},{"n":"2015","v":"2015"},{"n":"2014","v":"2014"},{"n":"2013","v":"2013"},{"n":"2012","v":"2012"},{"n":"2011","v":"2011"},{"n":"2010","v":"2010"},{"n":"2009","v":"2009"},{"n":"2008","v":"2008"},{"n":"2007","v":"2007"},{"n":"2006","v":"2006"},{"n":"2005","v":"2005"},{"n":"2004","v":"2004"},{"n":"2003","v":"2003"},{"n":"2002","v":"2002"},{"n":"2001","v":"2001"},{"n":"2000","v":"2000"}]},{"key":"month","name":"月份","value":[{"n":"全部","v":""},{"n":"12","v":"12"},{"n":"11","v":"11"},{"n":"10","v":"10"},{"n":"09","v":"09"},{"n":"08","v":"08"},{"n":"07","v":"07"},{"n":"06","v":"06"},{"n":"05","v":"05"},{"n":"04","v":"04"},{"n":"03","v":"03"},{"n":"02","v":"02"},{"n":"01","v":"01"}]}]
		}
		}
	#注意：这里不能带 Host 头——同一个 header 还要用于请求 CDN 域
	header = {
		"User-Agent":UA_STR,
		"Referer": REFERER_STR
	}
	
	#本地代理（兜底用：正常情况下本源直接把 CDN 原址交给播放器，不做中转）
	#  type=m3u8 -> 拉取清单，把分片/KEY 改写成代理地址后再交给播放器
	#  其它      -> 直接转发字节
	def localProxy(self,param):
		if isinstance(param, str):
			try:
				param = json.loads(param)
			except :
				param = {}
		if not isinstance(param, dict):
			param = {}
		low = {}
		for k in param:
			low[str(k).lower()] = param[k]
		target = low.get('url') or low.get('u') or low.get('src') or ''
		try:
			target = target.decode('utf-8')
		except :
			pass
		target = str(target)
		#宿主传进来的 url 可能是 URL 编码过的（https%3A%2F%2F...），必须按 '://' 判断后再解码
		if target.find('://') < 0:
			for _ in range(2):
				try:
					dec = urllib.parse.unquote(target)
				except :
					break
				if dec == target:
					break
				target = dec
		if target.find('http') != 0:
			return [404, "text/plain", b'', {'Access-Control-Allow-Origin':'*'}]
		hd = {'User-Agent':UA_STR, 'Referer':REFERER_STR}
		try:
			req = urllib.request.Request(url=target, headers=hd)
			with urllib.request.urlopen(req, timeout=20) as rsp:
				data = rsp.read()
				ctype = rsp.headers.get('Content-Type') or ''
		except :
			return [502, "text/plain", b'', {'Access-Control-Allow-Origin':'*'}]
		isM3u8 = target.split('?')[0].endswith('.m3u8') or ('mpegurl' in ctype.lower()) or (data[:64].find(b'#EXTM3U')>=0)
		if isM3u8:
			text = data.decode('utf-8', 'ignore')
			base = target.split('?')[0].rsplit('/', 1)[0] + '/'
			out = []
			for line in text.replace('\r', '').split('\n'):
				s = line.strip()
				if len(s)==0:
					out.append(line)
					continue
				if s[0]=='#':
					if 'URI="' in s:
						try:
							i0 = s.find('URI="') + 5
							i1 = s.find('"', i0)
							ku = s[i0:i1]
							if ku.find('http')!=0:
								ku = base + ku
							s = s[:i0] + PROXY_TS.format(urllib.parse.quote(ku, safe='')) + s[i1:]
						except :
							pass
					out.append(s)
					continue
				su = s if s.find('http')==0 else base + s
				out.append(PROXY_TS.format(urllib.parse.quote(su, safe='')))
			body = '\n'.join(out).encode('utf-8')
			return [200, "application/vnd.apple.mpegurl", body, {'Access-Control-Allow-Origin':'*'}]
		return [200, ctype if len(ctype)>0 else "video/mp2t", data, {'Access-Control-Allow-Origin':'*'}]
	#-----------------------------------------------自定义函数-----------------------------------------------
	#访问网页
	def webReadFile(self,urlStr,header):
		html=''
		req=urllib.request.Request(url=urlStr,headers=self.header)
		with  urllib.request.urlopen(req,timeout=20)  as response:
			html = response.read().decode('utf-8')
		return html
	#判断网络地址是否存在（异常返回 0，避免单个档位探测失败打断整条兜底链）
	def TestWebPage(self,urlStr,header):
		html=0
		try:
			req=urllib.request.Request(url=urlStr,method='HEAD')#,headers=header
			with  urllib.request.urlopen(req,timeout=10)  as response:
				html = response.getcode ()
		except Exception as e:
			html = 0
		return html
	#正则取文本
	def get_RegexGetText(self,Text,RegexText,Index):
		returnTxt=""
		Regex=re.search(RegexText, Text, re.M|re.S)
		if Regex is None:
			returnTxt=""
		else:
			returnTxt=Regex.group(Index)
		return returnTxt
	#取集数
	def get_EpisodesList(self,jsonList):
		videos=[]
		for vod in jsonList:
			url = vod['guid']
			title =vod['title']
			if len(url) == 0:
				continue
			videos.append(title+"$"+url)
		return videos
	#取集数
	def get_EpisodesList_re(self,htmlTxt,patternTxt):
		ListRe=re.finditer(patternTxt, htmlTxt, re.M|re.S)
		videos=[]
		for vod in ListRe:
			url = vod.group('url')
			title =vod.group('title')
			if len(url) == 0:
				continue
			videos.append(title+"$"+url)
		return videos
	#取剧集区
	def get_lineList(self,Txt,mark,after):
		circuit=[]
		origin=Txt.find(mark)
		while origin>8:
			end=Txt.find(after,origin)
			circuit.append(Txt[origin:end])
			origin=Txt.find(mark,end)
		return circuit	
	#正则取文本,返回数组	
	def get_RegexGetTextLine(self,Text,RegexText,Index):
		returnTxt=[]
		pattern = re.compile(RegexText, re.M|re.S)
		ListRe=pattern.findall(Text)
		if len(ListRe)<1:
			return returnTxt
		for value in ListRe:
			returnTxt.append(value)	
		return returnTxt
	#删除html标签
	def removeHtml(self,txt):
		soup = re.compile(r'<[^>]+>',re.S)
		txt =soup.sub('', txt)
		return txt.replace("&nbsp;"," ")
	#小体积探针：用 Range 只取前 4KB，靠 Content-Range / Content-Length 拿到分片总大小
	def readSmall(self,u,timeout=8):
		req=urllib.request.Request(url=u)
		req.add_header('User-Agent', UA_STR)
		req.add_header('Referer', REFERER_STR)
		req.add_header('Range', 'bytes=0-4095')
		with urllib.request.urlopen(req, timeout=timeout) as rsp:
			status=rsp.getcode()
			hh=rsp.headers
			data=rsp.read(4096)
		total=0
		cr=hh.get('Content-Range') or ''
		if '/' in cr:
			try :
				total=int(cr.split('/')[1])
			except :
				total=0
		if total==0:
			try :
				total=int(hh.get('Content-Length') or 0)
			except :
				total=0
		return status,total,data
	#探活：清单可拉 + 抽查首/中/尾三个分片
	#  ① 必须是 MPEG-TS（188 字节同步，0x47）
	#  ② 分片体积不得低于该档位理论码率的 55%（专门用来排除"清单 200 但画面被降级"的假高清）
	#只探清单是不够的：普通通道会返回 200 却把 1200 降级成 450 的画面，播出来就是花屏/糊成一片
	def probePlayable(self,u,quality=''):
		if len(u)==0:
			return False
		try:
			req=urllib.request.Request(url=u)
			req.add_header('User-Agent', UA_STR)
			req.add_header('Referer', REFERER_STR)
			with urllib.request.urlopen(req, timeout=8) as rsp:
				if rsp.getcode()!=200:
					return False
				txt=rsp.read().decode('utf-8','ignore')
		except :
			return False
		if '#EXTM3U' not in txt:
			return False
		segs=[]
		dur=10.0
		for line in txt.replace('\r','').split('\n'):
			s=line.strip()
			if s.find('#EXTINF')==0:
				dur=10.0
				try :
					dur=float(s.split(':')[1].split(',')[0])
				except :
					dur=10.0
			elif len(s)>0 and s[0]!='#':
				segs.append((s,dur))
		if len(segs)==0:
			return False
		base=u.split('?')[0].rsplit('/',1)[0]+'/'
		picks=[0, len(segs)//2, len(segs)-1]
		br=QUALITY_BITRATE.get(quality,0)
		for i in picks:
			s,dur=segs[i]
			seg = s if s.find('http')==0 else base+s
			try :
				st,total,data=self.readSmall(seg)
			except :
				return False
			if st not in (200,206):
				return False
			sync=0
			for o in range(0,min(len(data),1880),188):
				if data[o]==0x47:
					sync+=1
			if sync<5:
				return False
			if br>0 and total>0 and dur>0:
				need=int(br*1000/8.0*dur*SIZE_RATIO_MIN)
				if total<need:
					return False
		return True
	#取视频信息（接口每次下发的 CDN host 都是随机的；同一 pid 短时间缓存，避免一集请求两次）
	def getVideoInfo(self,pid):
		now=time.time()
		hit=_VINFO_CACHE.get(pid)
		if hit is not None and now-hit[0] < _VINFO_TTL:
			return hit[1]
		jo=None
		try :
			url="https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do?pid={0}".format(pid)
			txt=self.webReadFile(urlStr=url,header=self.header)
			jo=json.loads(txt)
			if jo.get('ack')!='yes':
				jo=None
			elif len((jo.get('hls_url') or '').strip())==0 and not jo.get('manifest'):
				jo=None
		except :
			jo=None
		#只缓存成功结果：接口偶发抖动不该被锁住 90 秒
		if jo is not None:
			if len(_VINFO_CACHE) > 128:
				_VINFO_CACHE.clear()
			_VINFO_CACHE[pid]=(now,jo)
		return jo
	#取出某档 MP4 分章的真实地址列表 [(url,duration)]
	#  chapters 数组本身永远存在（长度还挺像样），但 url 字段可能是空串 —— 空串代表"这条节目没开放明文 MP4"，
	#  这时必须当作没有，绝不能硬拼地址。
	def getMp4Chapters(self,pid,key):
		jo=self.getVideoInfo(pid)
		if jo is None:
			return []
		chapters=((jo.get('video') or {}).get(key) or [])
		segs=[]
		for c in chapters:
			try :
				u=(c.get('url') or '').strip()
			except :
				u=''
			if len(u)==0:
				continue
			try :
				dur=float(c.get('duration') or 0)
			except :
				dur=0.0
			if dur <= 0:
				dur=120.0
			segs.append((u,dur))
		return segs
	#该节目是否真的开放了明文 MP4 分章
	def hasMp4Chapters(self,pid,key):
		return len(self.getMp4Chapters(pid,key)) > 0
	#是不是"可直接播的媒体地址"（720P 线路的选集条目就是这种）
	def isMediaUrl(self,val):
		low=str(val).lower().split('?')[0]
		return low.endswith('.mp4') or low.endswith('.m3u8') or low.endswith('.ts') or low.endswith('.flv')
	#从选集条目 "名称$地址" 里取出可播的 pid：地址可能是 guid，也可能是需要解析的视频页
	def episodePid(self,item):
		parts=str(item).split('$')
		if len(parts) < 2:
			return ''
		val=parts[-1].strip()
		if len(val)==0:
			return ''
		if val.find('http') != 0:
			return val
		try :
			html=self.webReadFile(urlStr=val,header=self.header)
			return self.get_RegexGetText(Text=html,RegexText=r'var\sguid\s*=\s*"([^"]+)"',Index=1)
		except :
			return ''
	#把「明文 MP4 分章」铺成 720P 线路的选集。
	#  为什么拆成分段而不是做成一条 HLS：见文件头【实测 4】—— 各段是独立完整 MP4，
	#  ffmpeg(IJK) 与 ExoPlayer 都不支持把非分片 MP4 当 HLS 分片，只会播第 1 段。
	#  先探第 1 集：没有分章就整条 720P 线路都不出现，后面一集都不必再请求。
	def buildMp4Lines(self,videoList):
		if len(videoList) == 0:
			return []
		first=self.episodePid(videoList[0])
		if len(first) == 0:
			return []
		plan=[]
		for name,key in MP4_LEVELS:
			if self.hasMp4Chapters(first,key):
				plan.append((name,key))
		if len(plan) == 0:
			return []
		lines=[]
		for name,key in plan:
			eps=[]
			for i in range(len(videoList)):
				item=videoList[i]
				if i >= MAX_MP4_EPISODE:
					# 超过展开上限的集：原样列出（这些集仍可用 360P/270P 线路看）
					eps.append(item)
					continue
				pid=self.episodePid(item) if i > 0 else first
				segs=self.getMp4Chapters(pid,key) if len(pid) > 0 else []
				if len(segs) == 0:
					# 这一集没分章（同栏目里个别集可能不同）-> 原样列出，交给 360P 兜底
					eps.append(item)
					continue
				title=item.split('$')[0]
				for n in range(len(segs)):
					eps.append("{0} [{1}/{2}]${3}".format(title,n+1,len(segs),segs[n][0]))
			lines.append((name,"#".join(eps)))
		return lines
	#把模板里的档位占位(main)换成目标档位（保留官方 query，CDN 路由/鉴权可能依赖它）
	def buildQualityUrl(self,templateUrl,quality):
		if len(templateUrl) == 0:
			return ''
		base, sep, qs = templateUrl.partition('?')
		parts = base.split('/')
		for i in range(len(parts)):
			if parts[i] == 'main':
				parts[i] = quality
		parts[-1] = quality + '.m3u8'
		url = '/'.join(parts)
		if len(qs) > 0:
			url = url + '?' + qs
		return url
	#普通通道的档位顺序：目标档位优先，其余按 高清 -> 低清 兜底
	def getQualityOrder(self,quality):
		codes = list(PLAIN_SAFE_QUALITY)
		want = ''
		for name, src, code in QUALITY_LEVELS:
			if name == quality and src == 'plain':
				want = str(code)
		if len(want) > 0 and want in codes:
			codes.remove(want)
			codes.insert(0, want)
		return codes
	#取明文 HLS 普通通道的 m3u8 地址
	#  普通通道只提供 450/850；硬写 1200/2000 会拿到与 450 字节完全相同的降级流，
	#  所以必须靠 probePlayable 的分片体积校验把它挡掉，再逐档降级兜底。
	def get_m3u8(self,urlTxt,quality=''):
		try:
			jo = self.getVideoInfo(urlTxt)
		except :
			jo = None
		if jo is None:
			return ''
		plain = (jo.get('hls_url') or '').strip()
		if len(plain) == 0:
			return ''
		for code in self.getQualityOrder(quality):
			u = self.buildQualityUrl(plain, code)
			if len(u) == 0:
				continue
			if self.probePlayable(u, code):
				return u
		return ''
	#搜索
	def get_list_search(self,html,tid):
		jRoot = json.loads(html)
		jsonList=jRoot['list']
		videos=[]
		for vod in jsonList:
			url = vod['urllink']
			title =self.removeHtml(txt=vod['title'])
			img=vod['imglink']
			id=vod['id']
			brief=vod['channel']
			year=vod['uploadtime']
			if len(url) == 0:
				continue
			guid="{0}###{1}###{2}###{3}###{4}###{5}###{6}###{7}".format(tid,title,url,img,id,year,'',brief)
			videos.append({
				"vod_id":guid,
				"vod_name":title,
				"vod_pic":img,
				"vod_remarks":year
			})
		return videos
		return videos
	def get_list1(self,html,tid):
		jRoot = json.loads(html)
		videos = []
		data=jRoot['response']
		if data is None:
			return []
		jsonList=data['docs']
		for vod in jsonList:
			id = vod['lastVIDE']['videoSharedCode']
			title =vod['column_name']
			url=vod['column_website']
			img=vod['column_logo']
			year=vod['column_playdate']
			brief=vod['column_brief']
			actors=''
			if len(url) == 0:
				continue
			guid="{0}###{1}###{2}###{3}###{4}###{5}###{6}###{7}".format(tid,title,url,img,id,year,actors,brief)
			#print(vod_id)
			videos.append({
				"vod_id":guid,
				"vod_name":title,
				"vod_pic":img,
				"vod_remarks":''
			})
		#print(videos)
		return videos
	#分类取结果
	def get_list(self,html,tid):
		jRoot = json.loads(html)
		videos = []
		data=jRoot['data']
		if data is None:
			return []
		jsonList=data['list']
		for vod in jsonList:
			url = vod['url']
			title =vod['title']
			img=vod['image']
			id=vod['id']
			try:
				brief=vod['brief']
			except:
				brief=''
			try:
				year=vod['year']
			except:
				year=''
			try:
				actors=vod['actors']
			except:
				actors=''
			if len(url) == 0:
				continue
			guid="{0}###{1}###{2}###{3}###{4}###{5}###{6}###{7}".format(tid,title,url,img,id,year,actors,brief)
			#print(vod_id)
			videos.append({
				"vod_id":guid,
				"vod_name":title,
				"vod_pic":img,
				"vod_remarks":''
			})
		return videos
