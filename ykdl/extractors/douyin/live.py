# -*- coding: utf-8 -*-

from .._common import *
from .. import _byted


class Douyin(Extractor):
    name = '抖音直播 (Douyin)'

    quality_2_profile_id = {
        'ORIGION': ['原画', 'OG'],
        'FULL_HD1': ['蓝光', 'BD'],
        'HD1': ['超清', 'TD'],
        'SD1': ['高清', 'HD'],
        'SD2': ['标清', 'SD']
    }

    def prepare(self):
        info = MediaInfo(self.name)
        t = re.findall(r'live.douyin.com/(.+)', self.url)
        self.rid = t[0]

        if 'amemv.com' in self.url:
            data = get_response('https://webcast.amemv.com/webcast/room/reflow/info/',
                                params={
                                    'verifyFp': '',
                                    'type_id': 0,
                                    'live_id': 1,
                                    'sec_user_id': '',
                                    'app_id': 1128,
                                    'msToken': '',
                                    'X-Bogus': '',  # 1
                                    'room_id': match1(self.url, '/reflow/(\d+)')
                                }).json()
            video_info = data['data'].get('room')
        else:
            html = _byted.get_content(self.url)
            data = match1(html, r'self.__pace_f.push\(\[\d,("[a-z]:.+?")\]\)</script>')
            data = json.loads(data)
            data = json.loads(match1(data, r'(\[.+\])'))[-1]
            self.logger.debug('data: \n%s', data)

            try:
                video_info = data['state']['roomStore']['roomInfo'].get('room')
            except Exception as e:
                print(data)
                video_info = data['/webcast/reflow/:id'].get('room')

        # assert video_info and video_info['status'] == 2, 'live is off!!!'

        title = video_info['title']
        try:
            info.artist = nickName = video_info['owner']['nickname']
            info.title = '{title} - {nickName}'.format(**vars())

            if video_info['live_room_mode'] == 2:
                info.streams = False
            else:
                stream_info = video_info['stream_url']
                stream_urls = []
                if 'flv_pull_url' in stream_info:
                    for ql, url in stream_info['flv_pull_url'].items():
                        stream_urls.append(['flv', ql, url])
                    orig = stream_info.get('rtmp_pull_url')
                    if orig and orig not in stream_info['flv_pull_url'].values():
                        stream_urls.append(['flv', 'ORIGION', orig])
                if 'hls_pull_url_map' in stream_info:
                    for ql, url in stream_info['hls_pull_url_map'].items():
                        stream_urls.append(['m3u8', ql, url])
                    orig = stream_info.get('hls_pull_url')
                    if orig and orig not in stream_info['hls_pull_url_map'].values():
                        stream_urls.append(['m3u8', 'ORIGION', orig])

                for ext, ql, url in stream_urls:
                    if not url:
                        continue
                    stream_profile, stream_id = self.quality_2_profile_id[ql]
                    info.streams[stream_id + '-' + ext[:3]] = {
                        'container': ext,
                        'profile': stream_profile,
                        'src': [url],
                        'size': Infinity
                    }
        except:
            try:
                # info.artist = re.search(r'<title>(.*)的抖音直播间', html)[1]
                info.artist = data['state']['roomStore']['roomInfo']['anchor']['nickname']
            except:
                info.artist = False
            info.streams = False

        return info


site = Douyin()
