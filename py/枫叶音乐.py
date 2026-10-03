# coding=utf-8
# !/usr/bin/python

"""

作者 丢丢喵 🚓 内容均从互联网收集而来 仅供交流学习使用 版权归原创者所有 如侵犯了您的权益 请通知作者 将及时删除侵权内容
                    ====================Diudiumiao====================

改造说明：
    二级歌单不再使用 vod_tag:"folder" 进入三级列表，
    点击歌单时直接把该歌单的全部歌曲拼成 vod_play_url 交给播放器整单连播。
    vod_id 约定：
        歌单  ->  "歌单ID@歌单名"
        单曲  ->  歌曲直链（http 开头）

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

xurl = "https://fy-musicbox-api.mu-jie.cc"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.87 Safari/537.36'
          }

headerx = {
    "Host": "fy-musicbox-api.mu-jie.cc",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "sec-ch-ua-platform": '"Windows"',
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "sec-ch-ua": '"Microsoft Edge";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    "sec-ch-ua-mobile": "?0",
    "Accept": "*/*",
    "Origin": "https://mu-jie.cc",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://mu-jie.cc/",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "Accept-Encoding": "gzip, deflate"
          }

PLAY_FROM = "音乐专线"          # 详情页线路名
PLAY_ID_SEP = "@"               # vod_id 中歌单ID与歌单名的分隔符
MAX_TRACKS = 1000               # 单个歌单最多拼入的歌曲数，防止 vod_play_url 过长
TRACKS_TIMEOUT = 30             # 歌单歌曲接口超时（大歌单会慢）

_PLAYLIST_CACHE = {}            # 歌单ID -> (歌单名, 封面)，用于详情页补封面

class Spider(Spider):
    global xurl
    global headerx
    global headers

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

    def fetch_category_data(self):
        url = f'{xurl}/getPlaylistCategory'
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        data = detail.json()
        return data[0]['category']

    def process_category_item(self, vods):
        name = vods['name']
        return {"type_id": name, "type_name": name}

    def process_sub_categories(self, data1):
        sub_result = []
        for vods in data1:
            sub_result.append(self.process_category_item(vods))
        return sub_result

    def process_categories(self, data):
        result_classes = []
        for vod in data:
            data1 = vod['sub']
            result_classes.extend(self.process_sub_categories(data1))
        return result_classes

    def homeContent(self, filter):
        result = {"class": []}
        category_data = self.fetch_category_data()
        result["class"] = self.process_categories(category_data)
        return result

    def homeVideoContent(self):
        pass

    def fetch_playlist_tracks_data(self, playlist_id):
        url = f'{xurl}/meting/?server=netease&type=playlist&id={playlist_id}'
        try:
            detail = requests.get(url=url, headers=headerx, timeout=TRACKS_TIMEOUT)
            detail.encoding = "utf-8"
            return detail.json()
        except Exception:
            return {}

    def process_track_item(self, vod):
        name = vod['name']
        id = vod['url']
        pic = vod['pic']
        remark = vod['artist']
        return {
            "vod_id": id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": remark
                }

    def process_playlist_tracks(self, data):
        videos = []
        for vod in data['tracks']:
            video = self.process_track_item(vod)
            videos.append(video)
        return videos

    def fetch_category_playlists_data(self, cid):
        url = f'{xurl}/netease/playlist/category?type={cid}&limit=60'
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        return detail.json()

    def process_category_playlist_item(self, vod):
        name = vod['name']
        id = vod['id']
        pic = vod['coverImgUrl']
        remark = vod['playCount']
        # 缓存歌单名与封面，详情页可补图
        try:
            _PLAYLIST_CACHE[str(id)] = (name, pic)
        except Exception:
            pass
        # 不再标记 folder：点击歌单直接进入详情页，由 detailContent 输出整单播放列表
        return {
            "vod_id": f"{id}{PLAY_ID_SEP}{name}",
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": f"{remark} 播放量"
               }

    def process_category_playlists(self, data):
        videos = []
        for vod in data:
            video = self.process_category_playlist_item(vod)
            videos.append(video)
        return videos

    def build_category_result(self, videos, pg):
        result = {'list': videos}
        result['page'] = pg
        result['pagecount'] = 1
        result['limit'] = 90
        result['total'] = 999999
        return result

    def split_cid(self, cid):
        return cid.split("@")

    def categoryContent(self, cid, pg, filter, ext):
        videos = []
        if PLAY_ID_SEP in cid:
            fenge = self.split_cid(cid)
            data = self.fetch_playlist_tracks_data(fenge[0])
            videos = self.process_playlist_tracks(data)
        else:
            data = self.fetch_category_playlists_data(cid)
            videos = self.process_category_playlists(data)
        result = self.build_category_result(videos, pg)
        return result

    # ==================== 歌单（二级项）整单连播 ====================

    def get_playlist_info(self, did):
        """从 vod_id 中拆出 歌单ID 与 歌单名"""
        did = str(did)
        if PLAY_ID_SEP in did:
            playlist_id, name = did.split(PLAY_ID_SEP, 1)
        else:
            playlist_id, name = did, ''
        return playlist_id, name

    def clean_text(self, text):
        """清掉会破坏 vod_play_url 分隔符（$ # 换行）的字符"""
        text = str(text or '')
        text = text.replace('$', '').replace('#', '')
        text = text.replace('\r', ' ').replace('\n', ' ')
        return text.strip()

    def build_playlist_play_url(self, tracks):
        """把歌单歌曲数组拼成 TVBox 播放列表：歌名$地址#歌名$地址"""
        play_list = []
        used = {}
        for vod in tracks:
            if not isinstance(vod, dict):
                continue
            url = self.clean_text(vod.get('url'))
            if not url or 'http' not in url:
                continue
            name = self.clean_text(vod.get('name')) or '未知歌曲'
            # 歌名去重，避免同名曲目导致选集列表塌陷成只显示一条
            used[name] = used.get(name, 0) + 1
            if used[name] > 1:
                name = f'{name}({used[name]})'
            play_list.append(f'{name}${url}')
            if len(play_list) >= MAX_TRACKS:
                break
        return '#'.join(play_list)

    def create_playlist_detail_item(self, did):
        playlist_id, name = self.get_playlist_info(did)
        pic = _PLAYLIST_CACHE.get(str(playlist_id), ('', ''))[1]
        data = self.fetch_playlist_tracks_data(playlist_id)
        tracks = data.get('tracks') if isinstance(data, dict) else None
        play_url = self.build_playlist_play_url(tracks or [])
        if play_url:
            remarks = f"共{len(play_url.split('#'))}首"
        else:
            remarks = "歌单解析失败，请返回重试"
        return {
            "vod_id": did,
            "vod_name": name or "歌单",
            "vod_pic": pic,
            "vod_remarks": remarks,
            "vod_play_from": PLAY_FROM,
            "vod_play_url": play_url
               }

    def create_playlist_detail_list(self, did):
        return [self.create_playlist_detail_item(did)]

    # ==================== 单曲（搜索结果等） ====================

    def create_video_detail_item(self, did):
        return {
            "vod_id": did,
            "vod_play_from": PLAY_FROM,
            "vod_play_url": did
               }

    def create_videos_detail_list(self, did):
        videos = []
        video_item = self.create_video_detail_item(did)
        videos.append(video_item)
        return videos

    def build_detail_result(self, videos):
        result = {}
        result['list'] = videos
        return result

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            did = ids[0] if len(ids) > 0 else ''
        else:
            did = str(ids)
        if str(did).startswith('http'):
            # 单曲：直接把地址当作播放项
            videos = self.create_videos_detail_list(did)
        else:
            # 歌单：把三级（歌单内歌曲）内容直接作为该二级项的播放列表
            videos = self.create_playlist_detail_list(did)
        result = self.build_detail_result(videos)
        return result

    def get_redirect_location(self, id):
        try:
            response = requests.get(url=id, headers=headerx, allow_redirects=False, timeout=15)
            return response.headers.get('Location')
        except Exception:
            return None

    def build_player_result(self, url):
        result = {}
        result["parse"] = 0
        result["playUrl"] = ''
        result["url"] = url
        result["header"] = headers
        return result

    def playerContent(self, flag, id, vipFlags):
        url = self.get_redirect_location(id) or id
        result = self.build_player_result(url)
        return result

    def parse_search_page(self, pg):
        if pg:
            return int(pg)
        else:
            return 1

    def fetch_search_data(self, key, page):
        url = f'{xurl}/netease/search/song/?keywords={key}&pn={str(page)}&limit=20'
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        return detail.json()

    def process_search_result_item(self, vod):
        name = vod['name']
        id = vod['url']
        pic = vod['pic']
        remark = vod['artist']
        return {
            "vod_id": id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": remark
               }

    def process_search_results_list(self, data):
        videos = []
        for vod in data:
            video = self.process_search_result_item(vod)
            videos.append(video)
        return videos

    def build_search_result(self, videos, pg):
        result = {}
        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def searchContentPage(self, key, quick, pg):
        page = self.parse_search_page(pg)
        data = self.fetch_search_data(key, page)
        videos = self.process_search_results_list(data)
        result = self.build_search_result(videos, pg)
        return result

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
