# coding=utf-8
# !/usr/bin/python

"""

作者 丢丢喵 🚓 内容均从互联网收集而来 仅供交流学习使用 版权归原创者所有 如侵犯了您的权益 请通知作者 将及时删除侵权内容
                    ====================Diudiumiao====================

"""

from Crypto.Util.Padding import unpad
from Crypto.Util.Padding import pad
from urllib.parse import unquote
from Crypto.Cipher import ARC4
from urllib.parse import quote
from base.spider import Spider
from Crypto.Cipher import AES
from datetime import datetime
from bs4 import BeautifulSoup
from base64 import b64decode
import urllib.request
import urllib.parse
import datetime
import binascii
import requests
import base64
import json
import time
import sys
import re
import os

sys.path.append('..')

xurl = "http://read.api.duodutek.com"

headerx = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.87 Safari/537.36'
          }

class Spider(Spider):
    global xurl
    global headerx

    def getName(self):
        return "首页"

    def init(self, extend):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def extract_middle_text(self, text, start_str, end_str, pl, start_index1: str = '', end_index2: str = ''):
        if pl == 3:
            plx = []
            while True:
                start_index = text.find(start_str)
                if start_index == -1:
                    break
                end_index = text.find(end_str, start_index + len(start_str))
                if end_index == -1:
                    break
                middle_text = text[start_index + len(start_str):end_index]
                plx.append(middle_text)
                text = text.replace(start_str + middle_text + end_str, '')
            if len(plx) > 0:
                purl = ''
                for i in range(len(plx)):
                    matches = re.findall(start_index1, plx[i])
                    output = ""
                    for match in matches:
                        match3 = re.search(r'(?:^|[^0-9])(\d+)(?:[^0-9]|$)', match[1])
                        if match3:
                            number = match3.group(1)
                        else:
                            number = 0
                        if 'http' not in match[0]:
                            output += f"#{match[1]}${number}{xurl}{match[0]}"
                        else:
                            output += f"#{match[1]}${number}{match[0]}"
                    output = output[1:]
                    purl = purl + output + "$$$"
                purl = purl[:-3]
                return purl
            else:
                return ""
        else:
            start_index = text.find(start_str)
            if start_index == -1:
                return ""
            end_index = text.find(end_str, start_index + len(start_str))
            if end_index == -1:
                return ""

        if pl == 0:
            middle_text = text[start_index + len(start_str):end_index]
            return middle_text.replace("\\", "")

        if pl == 1:
            middle_text = text[start_index + len(start_str):end_index]
            matches = re.findall(start_index1, middle_text)
            if matches:
                jg = ' '.join(matches)
                return jg

        if pl == 2:
            middle_text = text[start_index + len(start_str):end_index]
            matches = re.findall(start_index1, middle_text)
            if matches:
                new_list = [f'{item}' for item in matches]
                jg = '$$$'.join(new_list)
                return jg

    def homeContent(self, filter):
        result = {}
        result = {"class": [{"type_id": "1287", "type_name": "甜宠"},
                            {"type_id": "1288", "type_name": "逆袭"},
                            {"type_id": "1289", "type_name": "热血"},
                            {"type_id": "1290", "type_name": "现代"},
                            {"type_id": "1291", "type_name": "古代"}],
                 }

        return result

    def homeVideoContent(self):
        pass

    def categoryContent(self, cid, pg, filter, ext):
        result = {}
        videos = []

        if pg:
            page = int(pg)
        else:
            page = 1

        url = f"{xurl}/novel-api/app/pageModel/getResourceById"

        params = {
            "productId": "2a8c14d1-72e7-498b-af23-381028eb47c0",
            "vestId": "2be070e0-c824-4d0e-a67a-8f688890cadb",
            "channel": "oppo19",
            "osType": "android",
            "version": "20",
            "token": "202509271001001446030204698626",
            "resourceId": cid,
            "pageNum": str(page),
            "pageSize": "10"
                 }

        detail = requests.get(url=url, headers=headerx, params=params)
        detail.encoding = "utf-8"
        data = detail.json()

        data = data['data']['datalist']

        for vod in data:

            name = vod['name']

            id = f"{vod['id']}@{vod['introduction']}"

            pic = vod['icon']

            remark = f"{vod['heat']}万播放"

            video = {
                "vod_id": id,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remark
                    }
            videos.append(video)

        result = {'list': videos}
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def detailContent(self, ids):
        did = ids[0]
        result = {}
        videos = []
        xianlu = ''
        bofang = ''

        fenge = did.split("@")

        url = f"{xurl}/novel-api/basedata/book/getChapterList"

        params = {
            "bookId": fenge[0],
            "productId": "2a8c14d1-72e7-498b-af23-381028eb47c0",
            "vestId": "2be070e0-c824-4d0e-a67a-8f688890cadb",
            "channel": "oppo19",
            "osType": "android",
            "version": "20",
            "token": "202509271001001446030204698626"
                 }

        detail = requests.get(url=url, headers=headerx, params=params, timeout=15)
        detail.encoding = "utf-8"
        data = detail.json()

        # 远端线路开关文件（fs-im-kefu.7moor-fs1.com 已失效），失败时直接走官方分集
        name, Jumps = '', ''
        try:
            url = 'https://fs-im-kefu.7moor-fs1.com/ly/4d2c3f00-7d4c-11e5-af15-41bf63ae4ea0/1732697392729/didiu.txt'
            response = requests.get(url, timeout=6)
            response.encoding = 'utf-8'
            code = response.text
            name = self.extract_middle_text(code, "s1='", "'", 0)
            Jumps = self.extract_middle_text(code, "s2='", "'", 0)
        except Exception:
            pass

        book = data['data']
        content = f"剧情介绍📢{fenge[1]}"

        # 官方分集为主线（bookName/iconUrl 用于详情页展示）
        book_name = ''
        book_pic = ''
        first = book[0] if isinstance(book, list) and book else {}
        book_name = first.get('bookName') or ''
        book_pic = first.get('iconUrl') or ''

        lines, urls = [], []
        if isinstance(book, list) and book:
            play = '#'.join(
                f"{vod.get('chapterName', '')}${vod['shortPlayList'][0]['chapterShortPlayVoList'][0]['shortPlayUrl']}"
                for vod in book if vod.get('shortPlayList'))
            if play:
                lines.append('短剧专线')
                urls.append(play)
        # 远端备用线路（原开关文件指向的线路），可用时作为第二线路追加
        if Jumps and Jumps.startswith('http'):
            lines.append('备用线路')
            urls.append(Jumps)
        bofang = '$$$'.join(urls)
        xianlu = '$$$'.join(lines)

        videos.append({
            "vod_id": did,
            "vod_name": book_name,
            "vod_pic": book_pic,
            "vod_play_from": xianlu,
            "vod_play_url": bofang
                     })

        result['list'] = videos
        return result

    def playerContent(self, flag, id, vipFlags):

        result = {}
        result["parse"] = 0
        result["playUrl"] = ''
        result["url"] = id
        result["header"] = headerx
        return result

    def searchContentPage(self, key, quick, pg):
        pass

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, '1')

    def localProxy(self, params):
        if params['type'] == "m3u8":
            return self.proxyM3u8(params)
        elif params['type'] == "media":
            return self.proxyMedia(params)
        elif params['type'] == "ts":
            return self.proxyTs(params)
        return None








