#!/usr/bin/env python
# -*- coding: utf-8 -*-

from .._common import *
from .util import get_h5enc, ub98484234
import time
import json
import uuid
import random
import string

douyu_match_pattern = [
    'class="hroom_id" value="([^"]+)',
    'data-room_id="([^"]+)'
]

def random_user_agent(device: str = 'desktop') -> str:
    import random
    chrome_version = random.randint(100, 120)
    if device == 'mobile':
        android_version = random.randint(9, 14)
        mobile = random.choice([
            'SM-G981B', 'SM-G9910', 'SM-S9080', 'SM-S9110', 'SM-S921B',
            'Pixel 5', 'Pixel 6', 'Pixel 7', 'Pixel 7 Pro', 'Pixel 8',
        ])
        return f'Mozilla/5.0 (Linux; Android {android_version}; {mobile}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Mobile Safari/537.36'
    return f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36'


class Douyutv(Extractor):
    name = '斗鱼直播 (DouyuTV)'

    stream_ids = ['OG', 'BD10M', 'BD8M', 'BD4M', 'BD', 'TD', 'HD', 'SD']
    profile_2_id = {
        '原画':    'OG',
        '蓝光10M': 'BD10M',
        '蓝光8M':  'BD8M',
        '蓝光4M':  'BD4M',
        '蓝光':    'BD',
        '超清':    'TD',
        '高清':    'HD',
        '流畅':    'SD'
     }

    def __init__(self):
        super().__init__()
        self.cnt = 0
        self.cdns = ['ws-h5', 'tct-h5']
        self.cnt2 = 1

        self.fake_headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-encoding': 'gzip, deflate, br, zstd',
            'accept-language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'user-agent': random_user_agent(),
        }
        self.fake_headers['referer'] = f"https://www.douyu.com"

    def prepare_mid(self):
        html = get_content(self.url)
        mid = match1(html, '\$ROOM\.room_id\s*=\s*(\d+)',
                           'room_id\s*=\s*(\d+)',
                           '"room_id.?":(\d+)',
                           'data-onlineid=(\d+)',
                           '(房间已被关闭)')
        assert mid != '房间已被关闭', '房间已被关闭'
        self.__req_query = {
            'cdn': 'hs-h5',
            'rate': '0',
            'ver': '219032101',
            'iar': '0', # ispreload? 1: 忽略 rate 参数，使用默认画质
            'ive': '0', # rate? 0~19 时、19~24 时请求数 >=3 为真
            'rid': mid,
            'hevc': '0',
            'fa': '0', # isaudio
            'sov': '0', # use wasm?
        }
        return mid

    def prepare(self):
        info = MediaInfo(self.name, True)

        add_header('Referer', 'https://www.douyu.com')
        html = get_content(self.url)

        title = match1(html, 'Title-head\w*">([^<]+)<')
        artist = match1(html, 'Title-anchorName\w*" title="([^"]+)"')
        if not title or not artist:
            room_data = get_response(
                    'https://open.douyucdn.cn/api/RoomApi/room/' + self.mid
                    ).json()
            if room_data['error'] == 0:
                room_data = room_data['data']
                title = room_data['room_name']
                artist = room_data['owner_name']

        info.title = '{title} - {artist}'.format(**vars())
        info.artist = artist

        js_enc = get_h5enc(html, self.mid)
        params = {
            'cdn': 'hw-h5',
            'iar': 0,
            'ive': 0,
        }
        ub98484234(js_enc, self.mid, self.logger, params)
        self.__req_query.update(params)

        def aget_mobile_play_info(req_query):
            url = f'https://m.douyu.com/api/room/ratestream'
            # elif preview:
            #     c_time_str = str(time.time_ns())
            #     url = f'https://playweb.douyucdn.cn/lapi/live/hlsH5Preview/{room_id}?{c_time_str[:18]}'
            #     data = {
            #         'rid': self.__room_id,
            #         'did': data.get('did', ["10000000000000000000000000001501"])[0],
            #     }
            #     req_headers.update({
            #         'Rid': self.__room_id,
            #         'Time': c_time_str[:13],
            #         'Auth': hashlib.md5(f"{self.__room_id}{c_time_str[:13]}".encode('utf-8')).hexdigest(),
            #     })
            rsp = get_response(
                url,
                headers={**self.fake_headers, 'user-agent': random_user_agent('mobile')},
                data=req_query
            )
            # rsp.raise_for_status()
            play_data = json.loads(rsp.text)
            if play_data['code'] != 0:
                raise ValueError(f"获取播放信息错误 {str(play_data)}")
            return play_data['data']

        def parse_stream_info(url):
            '''
            解析推流信息
            '''
            def get_tx_app_name(rtmp_url) -> str:
                '''
                获取腾讯云推流应用名
                '''
                host = rtmp_url.split('//')[1].split('/')[0]
                app_name = rtmp_url.split('/')[-1]
                # group 按顺序排序
                i = match1(host, r'.+(sa|3a|1a|3|1)')
                if i:
                    if i == "sa":
                        i = "1"
                    return f"dyliveflv{i}"
                return app_name
            list = url.split('?')
            query = {k: v[0] for k, v in parse_qs(list[1]).items()}
            stream_id = list[0].split('/')[-1].split('.')[0].split('_')[0]
            rtmp_url = list[0].split(stream_id)[0]
            return get_tx_app_name(rtmp_url[:-1]), stream_id, query

        def build_tx_url(tx_app_name, stream_id, query):
            '''
            构建腾讯CDN URL
            return: tx_url
            '''
            origin = query.get('origin', 'unknown')
            if origin not in ['tct', 'hw', 'dy']:
                '''
                dy: 斗鱼自建
                tct: 腾讯云
                hw: 华为云
                '''
                raise ValueError(f"当前流来源 {origin} 不支持切换为腾讯云推流")
            elif origin == 'dy':
                self.logger.warning(f": 当前流来源 {origin} 可能不存在腾讯云流")
            tx_host = "tc-tct.douyucdn2.cn"
            tx_url = f"https://{tx_host}/{tx_app_name}/{stream_id}.flv?%s"
            m_play_info = aget_mobile_play_info(self.__req_query)
            _, _, m_query = parse_stream_info(m_play_info['url'])
            # 需要移动端的宽松验证 token
            m_query.pop('vhost', None)
            query.update({
                'fcdn': 'tct',
                **m_query,
            })
            query = urlencode(query, doseq=True, encoding='utf-8')
            return tx_url % query

        def build_hs_url(url, is_tct):
            '''
            构建火山CDN URL
            :param url: 腾讯云 URL
            :param is_tct: 是否为 tct 流
            return: fake_hs_host, hs_cname_url
            '''
            tx_app_name, stream_id, query = parse_stream_info(url)
            # 必须从 tct 转 hs
            if not is_tct:
                url = build_tx_url(tx_app_name, stream_id, query)
            tx_host = url.split('//')[1].split('/')[0]
            hs_host = f"{tx_app_name.replace('dyliveflv', 'huos')}.douyucdn2.cn"
            hs_host = hs_host.replace('huos1.', 'huosa.')
            encoded_url = quote(url, safe='')
            query.update({
                'fp_user_url': encoded_url,
                'vhost': tx_host,
                'domain': tx_host,
            })
            query = urlencode(query, doseq=True, encoding='utf-8')
            hs_cname_host = "douyu-pull.s.volcfcdndvs.com"
            hs_cname_url = f"http://{hs_cname_host}/live/{stream_id}.flv?{query}"
            return (hs_host, hs_cname_url)


        def get_live_info(rate=0):
            params['rate'] = rate
            live_data = get_response(
                        'https://www.douyu.com/lapi/live/getH5Play/' + self.mid,
                        data=params).json()
            if live_data['error']:
                return live_data['msg']

            live_data = live_data['data']

            is_tct = live_data['rtmp_cdn'] == 'tct-h5'
            if live_data['rtmp_cdn'] != 'hs-h5':
                fake_host, cname_url = build_hs_url('/'.join([live_data['rtmp_url'], live_data['rtmp_live']]), is_tct)
                real_url = cname_url


            # real_url = '/'.join([live_data['rtmp_url'], live_data['rtmp_live']])
            rate_2_profile = {rate['rate']: rate['name']
                              for rate in live_data['multirates']}
            stream_profile = rate_2_profile[live_data['rate']]
            if '原画' in stream_profile:
                stream_id = 'OG'
            else:
                stream_id = self.profile_2_id[stream_profile]
            info.streams[stream_id] = {
                'container': match1(live_data['rtmp_live'], '\.(\w+)\?'),
                'profile': stream_profile,
                'src' : [real_url],
                'size': Infinity
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
        if error_msg:
            self.logger.debug('error_msg:\n\t' + error_msg)

        return info

    def prepare_list(self):
        html = get_content(self.url)
        return matchall(html, 'class="hroom_id" value="([^"]+)',
                              'data-room_id="([^"]+)')

site = Douyutv()
