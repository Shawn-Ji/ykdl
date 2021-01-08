#!/usr/bin/env python
# -*- coding: utf-8 -*-

from ykdl.util.html import get_content, add_header
from ykdl.util.match import match1, matchall
from ykdl.extractor import VideoExtractor
from ykdl.videoinfo import VideoInfo
from ykdl.compact import urlencode

from .util import get_h5enc, ub98484234

import time
import json
import uuid
import random
import string


douyu_match_pattern = [ 'class="hroom_id" value="([^"]+)',
                        'data-room_id="([^"]+)'
                      ]

def get_room_info(vid):
    html = get_content('https://open.douyucdn.cn/api/RoomApi/room/' + vid)
    room_data = json.loads(html)
    if room_data['error'] == 0:
        return room_data['data']

def get_random_name(l):
    return random.choice(string.ascii_letters) + \
           ''.join(random.sample(string.ascii_letters + string.digits, l - 1))


class Douyutv(VideoExtractor):
    name = u'斗鱼直播 (DouyuTV)'

    stream_ids = ['OG', 'BD10M', 'BD8M', 'BD4M', 'BD', 'TD', 'HD', 'SD']
    profile_2_id = {
        u'原画': 'OG',
        u'蓝光10M': 'BD10M',
        u'蓝光8M': 'BD8M',
        u'蓝光4M': 'BD4M',
        u'蓝光': 'BD',
        u'超清': 'TD',
        u'高清': 'HD',
        u'流畅': 'SD'
     }

    def __init__(self):
        super().__init__()
        self.cnt = 0
        self.cdns = ['ws-h5', 'tct-h5']

    def prepare(self):
        info = VideoInfo(self.name, True)
        add_header("Referer", 'https://www.douyu.com')

        html = get_content(self.url)
        self.vid = match1(html, '\$ROOM\.room_id\s*=\s*(\d+)',
                                'room_id\s*=\s*(\d+)',
                                '"room_id.?":(\d+)',
                                'data-onlineid=(\d+)')

        title = match1(html, 'Title-head\w*">([^<]+)<')
        artist = match1(html, 'Title-anchorName\w*" title="([^"]+)"')
        if not title or not artist:
            room_data = json.loads(get_content('https://open.douyucdn.cn/api/RoomApi/room/' + self.vid))
            if room_data['error'] == 0:
                room_data = room_data['data']
                title = room_data['room_name']
                artist = room_data['owner_name']

        info.title = u'{} - {}'.format(title, artist)
        info.artist = artist

        js_enc = get_h5enc(html, self.vid)
        params = {
            'cdn': '',
            'iar': 0,
            'ive': 0
        }
        ub98484234(js_enc, self, params)

        def get_live_info(rate=0):
            params['rate'] = rate
            # params['cdn'] = self.cdns[self.cnt % len(self.cdns)]
            params['cdn'] = self.cdns[random.randint(0, len(self.cdns) - 1)]
            data = urlencode(params)
            if not isinstance(data, bytes):
                data = data.encode()
            html_content = get_content('https://www.douyu.com/lapi/live/getH5Play/{}'.format(self.vid), data=data)
            self.logger.debug(html_content)

            live_data = json.loads(html_content)
            if live_data['error']:
                return live_data['msg']

            live_data = live_data["data"]

            for cdn in live_data['cdnsWithName']:
                if not cdn['cdn']in self.cdns:
                    self.cdns.append(cdn['cdn'])

            real_url = '{}/{}'.format(live_data['rtmp_url'], live_data['rtmp_live'])
            rate_2_profile = dict((rate['rate'], rate['name']) for rate in live_data['multirates'])
            video_profile = rate_2_profile[live_data['rate']]
            stream = self.profile_2_id[video_profile]
            if stream in info.streams:
                return
            info.stream_types.append(stream)
            info.streams[stream] = {
                'container': match1(live_data['rtmp_live'], '\.(\w+)\?'),
                'video_profile': video_profile,
                'src' : [real_url],
                'size': float('inf')
            }

            error_msges = []
            if rate == 0:
                rate_2_profile.pop(0, None)
                rate_2_profile.pop(live_data['rate'], None)
                for rate in rate_2_profile:
                    error_msg = get_live_info(rate)
                    if error_msg:
                        error_msges.append(error_msg)
            if error_msges:
                return ', '.join(error_msges)

        error_msg = get_live_info()
        assert len(info.stream_types), error_msg
        info.stream_types = sorted(info.stream_types, key=self.stream_ids.index)
        self.cnt += 1
        return info

    def prepare_list(self):

        html = get_content(self.url)
        return matchall(html, douyu_match_pattern)

site = Douyutv()
