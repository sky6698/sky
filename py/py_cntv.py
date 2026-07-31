#coding=utf-8
#!/usr/bin/python
import sys
sys.path.append('..')
from base.spider import Spider
import json
import time
import base64
import re
from urllib import request, parse
import urllib
import urllib.request
import time

class Spider(Spider):
	def getName(self):
		return "中央电视台"
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
		month = ""
		year = ""
		area=''
		channel=''
		datafl=''
		letter=''
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
			cid=''
			if 'cid' in extend.keys():
				cid=extend['cid']
			fc=''
			if 'fc' in extend.keys():
				fc=extend['fc']
			fl=''
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

		result['list'] = videos
		result['page'] = pg
		result['pagecount'] = 9999 if len(videos)>=pagecount else pg
		result['limit'] = 90
		result['total'] = 999999
		return result
	def detailContent(self,array):
		result={}
		aid = array[0].split('###')
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
		vod['vod_play_from'] = fromId
		vod['vod_play_url'] = "#".join(videoList)
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
	def searchContent(self,key,quick):
		return self.searchContentPage(key, quick, '1')
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
		# 使用PC端UA，部分CDN对移动端UA返回低码率
		headers = {
			'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
			'Referer':'https://tv.cctv.com/',
			'Origin':'https://tv.cctv.com'
		}
		if flag=='CCTV':
			url=self.get_m3u8(urlTxt=id)
		else:
			try:
				html=self.webReadFile(urlStr=id,header=self.header)
				guid=self.get_RegexGetText(Text=html,RegexText=r'var\sguid\s*=\s*"(.+?)";',Index=1)
				url=self.get_m3u8(urlTxt=guid)
			except :
				url=id
				parse=1
		if url.find('https:')<0:
			url=id
			parse=1
		result["parse"] = parse
		result["playUrl"] = ''
		result["url"] = url
		result["header"] = headers
		return result

	# ============================== 清晰度配置 ==============================
	# 码率对照表（数字越大清晰度越高）：
	#   450  = 流畅  (360x240)
	#   850  = 标清  (480x360)
	#  1200  = 高清  (720x576)
	#  2000  = 超清  (720p)
	#  3000  = 蓝光新
	#  4000  = 蓝光  (最高)
	# 修改下方 MAX_BITRATE 即可切换清晰度，默认 4000（蓝光最高）
	# =======================================================================
	MAX_BITRATE = 4000

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
		{"key":"datapd-channel","name":"频道","value":[{"n":"全部","v":""},{"n":"CCTV-1 综合","v":"CCTV-1 综合"},{"n":"CCTV-2 财经","v":"CCTV-2 财经"},{"n":"CCTV-3 综艺","v":"CCTV-3 综艺"},{"n":"CCTV-4 中文国际","v":"CCTV-4 中文国际"},{"n":"CCTV-5 体育","v":"CCTV-5 体育"},{"n":"CCTV-6 电影","v":"CCTV-6 电影"},{"n":"CCTV-7 国防军事","v":"CCTV-7 国防军事"},{"n":"CCTV-8 电视剧","v":"CCTV-8 电视剧"},{"n":"CCTV-9 纪录","v":"CCTV-9 纪录"},{"n":"CCTV-10 科教","v":"CCTV-10 科教"},{"n":"CCTV-11 戏曲","v":"CCTV-11 戏曲"},{"n":"CCTV-12 社会与法","v":"CCTV-12 社会与法"},{"n":"CCTV-13 新闻","v":"CCTV-13 新闻"},{"n":"CCTV-14 少儿","v":"CCTV-14 少儿"},{"n":"CCTV-15 音乐","v":"CCTV-15 音乐"},{"n":"CCTV-17 农业农村","v":"CCTV-17 农业农村"}]},
		{"key":"datafl-sc","name":"类型","value":[{"n":"全部","v":""},{"n":"人文历史","v":"人文历史"},{"n":"人物","v":"人物"},{"n":"军事","v":"军事"},{"n":"探索","v":"探索"},{"n":"社会","v":"社会"},{"n":"时政","v":"时政"},{"n":"经济","v":"经济"},{"n":"科技","v":"科技"}]},
		{"key":"datanf-year","name":"年份","value":[{"n":"全部","v":""},{"n":"2023","v":"2023"},{"n":"2022","v":"2022"},{"n":"2021","v":"2021"},{"n":"2020","v":"2020"},{"n":"2019","v":"2019"},{"n":"2018","v":"2018"},{"n":"2017","v":"2017"},{"n":"2016","v":"2016"},{"n":"2015","v":"2015"},{"n":"2014","v":"2014"},{"n":"2013","v":"2013"},{"n":"2012","v":"2012"},{"n":"2011","v":"2011"},{"n":"2010","v":"2010"},{"n":"2009","v":"2009"},{"n":"2008","v":"2008"}]},
		{"key":"dataszm-letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"C","v":"C"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0-9"}]}
		],
		"特别节目":[
		{"key":"datapd-channel","name":"频道","value":[{"n":"全部","v":""},{"n":"CCTV-1 综合","v":"CCTV-1 综合"},{"n":"CCTV-2 财经","v":"CCTV-2 财经"},{"n":"CCTV-3 综艺","v":"CCTV-3 综艺"},{"n":"CCTV-4 中文国际","v":"CCTV-4 中文国际"},{"n":"CCTV-5 体育","v":"CCTV-5 体育"},{"n":"CCTV-6 电影","v":"CCTV-6 电影"},{"n":"CCTV-7 国防军事","v":"CCTV-7 国防军事"},{"n":"CCTV-8 电视剧","v":"CCTV-8 电视剧"},{"n":"CCTV-9 纪录","v":"CCTV-9 纪录"},{"n":"CCTV-10 科教","v":"CCTV-10 科教"},{"n":"CCTV-11 戏曲","v":"CCTV-11 戏曲"},{"n":"CCTV-12 社会与法","v":"CCTV-12 社会与法"},{"n":"CCTV-13 新闻","v":"CCTV-13 新闻"},{"n":"CCTV-14 少儿","v":"CCTV-14 少儿"},{"n":"CCTV-15 音乐","v":"CCTV-15 音乐"},{"n":"CCTV-17 农业农村","v":"CCTV-17 农业农村"}]},
		{"key":"datafl-sc","name":"类型","value":[{"n":"全部","v":""},{"n":"新闻","v":"新闻"},{"n":"经济","v":"经济"},{"n":"综艺","v":"综艺"},{"n":"体育","v":"体育"},{"n":"军事","v":"军事"},{"n":"影视","v":"影视"},{"n":"科教","v":"科教"},{"n":"戏曲","v":"戏曲"},{"n":"青少","v":"青少"},{"n":"音乐","v":"音乐"},{"n":"社会","v":"社会"},{"n":"公益","v":"公益"},{"n":"其他","v":"其他"}]},
		{"key":"dataszm-letter","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"C","v":"C"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"},{"n":"0-9","v":"0-9"}]}
		],
		"节目大全":[{"key":"cid","name":"频道","value":[{"n":"全部","v":""},{"n":"CCTV-1综合","v":"EPGC1386744804340101"},{"n":"CCTV-2财经","v":"EPGC1386744804340102"},{"n":"CCTV-3综艺","v":"EPGC1386744804340103"},{"n":"CCTV-4中文国际","v":"EPGC1386744804340104"},{"n":"CCTV-5体育","v":"EPGC1386744804340107"},{"n":"CCTV-6电影","v":"EPGC1386744804340108"},{"n":"CCTV-7国防军事","v":"EPGC1386744804340109"},{"n":"CCTV-8电视剧","v":"EPGC1386744804340110"},{"n":"CCTV-9纪录","v":"EPGC1386744804340112"},{"n":"CCTV-10科教","v":"EPGC1386744804340113"},{"n":"CCTV-11戏曲","v":"EPGC1386744804340114"},{"n":"CCTV-12社会与法","v":"EPGC1386744804340115"},{"n":"CCTV-13新闻","v":"EPGC1386744804340116"},{"n":"CCTV-14少儿","v":"EPGC1386744804340117"},{"n":"CCTV-15音乐","v":"EPGC1386744804340118"},{"n":"CCTV-16奥林匹克","v":"EPGC1634630207058998"},{"n":"CCTV-17农业农村","v":"EPGC1563932742616872"},{"n":"CCTV-5+体育赛事","v":"EPGC1468294755566101"}]},{"key":"fc","name":"分类","value":[{"n":"全部","v":""},{"n":"新闻","v":"新闻"},{"n":"体育","v":"体育"},{"n":"综艺","v":"综艺"},{"n":"健康","v":"健康"},{"n":"生活","v":"生活"},{"n":"科教","v":"科教"},{"n":"经济","v":"经济"},{"n":"农业","v":"农业"},{"n":"法治","v":"法治"},{"n":"军事","v":"军事"},{"n":"少儿","v":"少儿"},{"n":"动画","v":"动画"},{"n":"纪实","v":"纪实"},{"n":"戏曲","v":"戏曲"},{"n":"音乐","v":"音乐"},{"n":"影视","v":"影视"}]},{"key":"fl","name":"字母","value":[{"n":"全部","v":""},{"n":"A","v":"A"},{"n":"B","v":"B"},{"n":"C","v":"C"},{"n":"D","v":"D"},{"n":"E","v":"E"},{"n":"F","v":"F"},{"n":"G","v":"G"},{"n":"H","v":"H"},{"n":"I","v":"I"},{"n":"J","v":"J"},{"n":"K","v":"K"},{"n":"L","v":"L"},{"n":"M","v":"M"},{"n":"N","v":"N"},{"n":"O","v":"O"},{"n":"P","v":"P"},{"n":"Q","v":"Q"},{"n":"R","v":"R"},{"n":"S","v":"S"},{"n":"T","v":"T"},{"n":"U","v":"U"},{"n":"V","v":"V"},{"n":"W","v":"W"},{"n":"X","v":"X"},{"n":"Y","v":"Y"},{"n":"Z","v":"Z"}]},{"key":"year","name":"年份","value":[{"n":"全部","v":""},{"n":"2023","v":"2023"},{"n":"2022","v":"2022"},{"n":"2021","v":"2021"},{"n":"2020","v":"2020"},{"n":"2019","v":"2019"},{"n":"2018","v":"2018"},{"n":"2017","v":"2017"},{"n":"2016","v":"2016"},{"n":"2015","v":"2015"},{"n":"2014","v":"2014"},{"n":"2013","v":"2013"},{"n":"2012","v":"2012"},{"n":"2011","v":"2011"},{"n":"2010","v":"2010"},{"n":"2009","v":"2009"},{"n":"2008","v":"2008"},{"n":"2007","v":"2007"},{"n":"2006","v":"2006"},{"n":"2005","v":"2005"},{"n":"2004","v":"2004"},{"n":"2003","v":"2003"},{"n":"2002","v":"2002"},{"n":"2001","v":"2001"},{"n":"2000","v":"2000"}]},{"key":"month","name":"月份","value":[{"n":"全部","v":""},{"n":"12","v":"12"},{"n":"11","v":"11"},{"n":"10","v":"10"},{"n":"09","v":"09"},{"n":"08","v":"08"},{"n":"07","v":"07"},{"n":"06","v":"06"},{"n":"05","v":"05"},{"n":"04","v":"04"},{"n":"03","v":"03"},{"n":"02","v":"02"},{"n":"01","v":"01"}]}]
		}
		}
	header = {
		"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
		"Host": "tv.cctv.com",
		"Referer": "https://tv.cctv.com/"
	}

	def localProxy(self,param):
		return [200, "video/MP2T", action, ""]

	# ----------------------------------------------- 自定义函数 -----------------------------------------------

	def webReadFile(self,urlStr,header):
		html=''
		req=urllib.request.Request(url=urlStr)
		with urllib.request.urlopen(req) as response:
			html = response.read().decode('utf-8')
		return html

	def TestWebPage(self,urlStr,header=None):
		try:
			req=urllib.request.Request(url=urlStr,method='HEAD')
			with urllib.request.urlopen(req, timeout=5) as response:
				return response.getcode()
		except:
			return 0

	def get_RegexGetText(self,Text,RegexText,Index):
		returnTxt=""
		Regex=re.search(RegexText, Text, re.M|re.S)
		if Regex is None:
			returnTxt=""
		else:
			returnTxt=Regex.group(Index)
		return returnTxt

	def get_EpisodesList(self,jsonList):
		videos=[]
		for vod in jsonList:
			url = vod['guid']
			title =vod['title']
			if len(url) == 0:
				continue
			videos.append(title+"$"+url)
		return videos

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

	def removeHtml(self,txt):
		soup = re.compile(r'<[^>]+>',re.S)
		txt =soup.sub('', txt)
		return txt.replace("&nbsp;"," ")

	# ============================== 核心修改：get_m3u8 ==============================
	# CNTV 清晰度由 URL 中的码率值控制，格式为：
	#   https://{CDN域名}/asp/hls/{BITRATE}/0303000a/3/default/{GUID}/{BITRATE}.m3u8
	#
	# 原代码的问题：
	#   1. 把路径中的 main 硬编码替换成 1200（仅高清），不是最高
	#   2. 从 master playlist 解析变体，但 CDN 有防护无法直接拉取
	#   3. hls_url 自带 maxbr=2048 参数，限制了最高码率
	#
	# 新方案：直接从 hls_url 解析出 GUID，构造最高码率（默认4000蓝光）的直链，
	# 遍历多个 CDN 域名做可用性检测，命中即返回。
	# ================================================================================
	def get_m3u8(self,urlTxt):
		# 1. 请求 API 拿到 hls_url
		api = "https://vdn.apps.cntv.cn/api/getHttpVideoInfo.do?pid={0}".format(urlTxt)
		try:
			html = self.webReadFile(urlStr=api, header=self.header)
			jo = json.loads(html)
		except Exception as e:
			print("[get_m3u8] API请求失败: " + str(e))
			return ""

		# 2. 提取 GUID（在 default/ 和 /main.m3u8 之间）
		hls_url = jo.get('hls_url', '').strip()
		if not hls_url:
			print("[get_m3u8] hls_url 为空")
			return ""

		m = re.search(r'default/([a-f0-9]+)/', hls_url)
		if not m:
			print("[get_m3u8] 无法从 hls_url 解析 GUID: " + hls_url)
			return ""
		guid = m.group(1)

		# 3. 定义码率优先级（从高到低），依次尝试
		#    4000=蓝光, 3000=蓝光新, 2000=超清, 1200=高清
		bitrates = [4000, 3000, 2000, 1200]

		# 4. 多个 CDN 域名备选（部分域名对某些IP段有限制）
		cdn_domains = [
			"hls.cntv.cdn20.com",
			"hls.cntv.lxdns.com",
			"hls.cntv.kcdnvip.com",
			"hls.cntv.myhwcdn.cn",
		]

		# 5. 遍历码率 × CDN，返回第一个可用的 URL
		for br in bitrates:
			for domain in cdn_domains:
				url = "https://{0}/asp/hls/{1}/0303000a/3/default/{2}/{1}.m3u8".format(domain, br, guid)
				try:
					code = self.TestWebPage(urlStr=url, header=self.header)
					if code == 200:
						print("[get_m3u8] 命中清晰度 {0}kbps, CDN={1}".format(br, domain))
						return url
				except:
					continue

		# 6. 全部失败，退回到原始 hls_url（可能受 maxbr 限制，但至少能播）
		print("[get_m3u8] 所有CDN均不可达，退回原始 hls_url")
		return hls_url

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
			videos.append({
				"vod_id":guid,
				"vod_name":title,
				"vod_pic":img,
				"vod_remarks":''
			})
		return videos

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
			videos.append({
				"vod_id":guid,
				"vod_name":title,
				"vod_pic":img,
				"vod_remarks":''
			})
		return videos
