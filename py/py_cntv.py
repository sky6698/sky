# coding=utf-8
#!/usr/bin/python
import sys
sys.path.append('..')
from base.spider import Spider
import json
import re
import urllib.request

class Spider(Spider):
    def getName(self):
        return "中央电视台"

    def init(self, extend=""):
        pass

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        return url.endswith('.m3u8')

    def manualVideoCheck(self):
        pass

    # ================== 首页 ==================
    def homeContent(self, filter):
        result = {}
        cateManual = {
            "央视大全": "节目大全",
            "电视剧": "电视剧",
            "动画片": "动画片",
            "纪录片": "纪录片",
            "特别节目": "特别节目"
        }
        classes = []
        for k in cateManual:
            classes.append({
                'type_name': k,
                'type_id': cateManual[k]
            })
        result['class'] = classes
        if filter:
            result['filters'] = self.config['filter']
        return result

    def homeVideoContent(self):
        return {'list': []}

    # ================== 分类 ==================
    def categoryContent(self, tid, pg, filter, extend):
        area, year, channel, datafl, letter = '', '', '', '', ''
        pagecount = 24

        if tid == '动画片':
            fc = urllib.parse.quote(tid)
            datafl = urllib.parse.quote(extend.get('datafl-sc', ''))
            area = urllib.parse.quote(extend.get('datadq-area', ''))
            letter = extend.get('dataszm-letter', '')
            url = (
                'https://api.cntv.cn/list/getVideoAlbumList?'
                'channelid=CHAL1460955899450127&area={}&sc={}&fc={}'
                '&letter={}&p={}&n=24&serviceId=tvcctv&topv=1&t=json'
            ).format(area, datafl, fc, letter, pg)

        elif tid == '纪录片':
            fc = urllib.parse.quote(tid)
            channel = urllib.parse.quote(extend.get('datapd-channel', ''))
            datafl = urllib.parse.quote(extend.get('datafl-sc', ''))
            year = extend.get('datanf-year', '')
            letter = extend.get('dataszm-letter', '')
            url = (
                'https://api.cntv.cn/list/getVideoAlbumList?'
                'channelid=CHAL1460955924871139&fc={}&channel={}&sc={}'
                '&year={}&letter={}&p={}&n=24&serviceId=tvcctv&topv=1&t=json'
            ).format(fc, channel, datafl, year, letter, pg)

        elif tid == '电视剧':
            fc = urllib.parse.quote(tid)
            datafl = urllib.parse.quote(extend.get('datafl-sc', ''))
            year = extend.get('datanf-year', '')
            letter = extend.get('dataszm-letter', '')
            url = (
                'https://api.cntv.cn/list/getVideoAlbumList?'
                'channelid=CHAL1460955853485115&area={}&sc={}&fc={}'
                '&year={}&letter={}&p={}&n=24&serviceId=tvcctv&topv=1&t=json'
            ).format(area, datafl, fc, year, letter, pg)

        elif tid == '特别节目':
            fc = urllib.parse.quote(tid)
            channel = urllib.parse.quote(extend.get('datapd-channel', ''))
            datafl = urllib.parse.quote(extend.get('datafl-sc', ''))
            letter = extend.get('dataszm-letter', '')
            url
