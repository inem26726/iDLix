"""
Helper Class for iDLix
Originate from IDLIX Downloader & IDLIX Player CLI (https://github.com/sandrocods/IdlixDownloader)

Author      : sandroputraa - https://github.com/sandrocods
Co-Author   : gopelkujo - https://github.com/gopelkujo
Update      : 07-01-2025
"""
import os
import random
import re
import json
import m3u8
import shutil
import requests
import m3u8_To_MP4
from loguru import logger
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse
from vtt_to_srt.vtt_to_srt import ConvertFile
from curl_cffi import requests as cffi_requests
from src.CryptoJsAesHelper import CryptoJsAes, dec


class IdlixHelper:
    BASE_WEB_URL = "https://tv7.idlix.asia/"
    BASE_STATIC_HEADERS = {
        "Host": "tv7.idlix.asia",
        "Connection": "keep-alive",
        "sec-ch-ua": "Not)A;Brand;v=99, Google Chrome;v=127, Chromium;v=127",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "Windows",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Dest": "document",
        "Referer": BASE_WEB_URL,
        "Accept-Language": "en-US,en;q=0.9,id;q=0.8"
    }

    def __init__(self):
        self.poster = None
        self.m3u8_url = None
        self.video_id = None
        self.embed_url = None
        self.video_name = None
        self.is_subtitle = None
        self.variant_playlist = None
        self.request = cffi_requests.Session(
            impersonate=random.choice(["chrome124", "chrome119", "chrome104"]),
            headers=self.BASE_STATIC_HEADERS,
            debug=False
        )

    # TODO: Refactor get_movie_data() and get_series_data()
    def get_movie_data(self, url):
        if not url:
            return {
                'status': False,
                'message': 'URL is required'
            }
        if not url.startswith(self.BASE_WEB_URL):
            return {
                'status': False,
                'message': 'Invalid URL'
            }
        try:
            request = self.request.get(
                url=url,
            )
            if request.status_code != 200:
                return {
                    'status': False,
                    'message': 'Failed to get video data'
                }

            bs = BeautifulSoup(request.text, 'html.parser')
            meta_counter = bs.find('meta', {'id': 'dooplay-ajax-counter'})
            meta_name = bs.find('meta', {'itemprop': 'name'})
            image = bs.find('img', {'itemprop': 'image'})

            # bs.find() returns None when the page is a block/interstitial page
            # or the layout changed; the original chained .get() straight onto it
            # and crashed with AttributeError before any status could be read.
            if not meta_counter or not meta_name:
                return {
                    'status': False,
                    'message': 'Video metadata not found (unexpected page layout)'
                }

            self.video_id = meta_counter.get('data-postid')
            self.video_name = unquote(meta_name.get('content') or '')
            self.poster = image.get('src') if image else None
            return {
                'status': True,
                'video_id': self.video_id,
                'video_name': self.video_name,
                'poster': self.poster
            }
        except Exception as error_get_movie_data:
            return {
                'status': False,
                'message': str(error_get_movie_data)
            }

    def get_series_data(self, url):
        if not url:
            return {
                'status': False,
                'message': 'URL is required'
            }
        if not url.startswith(self.BASE_WEB_URL):
            return {
                'status': False,
                'message': 'Invalid URL'
            }
        try:
            request = self.request.get(
                url=url,
            )
            if request.status_code != 200:
                return {
                    'status': False,
                    'message': 'Failed to get video data'
                }

            bs = BeautifulSoup(request.text, 'html.parser')
            meta_counter = bs.find('meta', {'id': 'dooplay-ajax-counter'})
            episode_title = bs.find('h1', {'class': 'epih1'})

            # same None-chaining crash as get_movie_data(): find() returns None
            # on a block page or a layout change, and .getText()/.get() would
            # raise AttributeError with no status to report back.
            if not meta_counter or not episode_title:
                return {
                    'status': False,
                    'message': 'Video metadata not found (unexpected page layout)'
                }

            self.video_id = meta_counter.get('data-postid')
            self.video_name = unquote(episode_title.get_text())
            self.poster = 'no-poster'
            return {
                'status': True,
                'video_id': self.video_id,
                'video_name': self.video_name,
                'poster': self.poster
            }
        except Exception as error_get_series_data:
            return {
                'status': False,
                'message': str(error_get_series_data)
            }

    def get_embed_url(self):
        if not self.video_id:
            return {
                'status': False,
                'message': 'Video ID is required'
            }
        try:
            request = self.request.post(
                url=self.BASE_WEB_URL + "wp-admin/admin-ajax.php",
                data={
                    "action": "doo_player_ajax",
                    "post": self.video_id,
                    "nume": "1",
                    "type": "movie",
                }
            )
            if request.status_code == 200 and request.json().get('embed_url'):
                self.embed_url = CryptoJsAes.decrypt(
                    request.json().get('embed_url'),
                    dec(
                        request.json().get('key'),
                        json.loads(request.json().get('embed_url')).get('m')
                    )
                )
                return {
                    'status': True,
                    'embed_url': self.embed_url
                }
            else:
                return {
                    'status': False,
                    'message': 'Failed to get embed URL'
                }
        except Exception as error_get_embed_url:
            return {
                'status': False,
                'message': str(error_get_embed_url)
            }

    def get_m3u8_url(self):
        if not self.embed_url:
            return {
                'status': False,
                'message': 'Embed URL is required'
            }

        # This block used to sit outside the try below and indexed blind:
        # path.split('/')[2] raises IndexError on a short path, and
        # query.split('=')[1] raises IndexError whenever the query is empty or
        # has no '='. Both escaped as a raw traceback.
        try:
            parsed_embed = urlparse(self.embed_url)
            if '/video/' in parsed_embed.path:
                video_path_parts = parsed_embed.path.split('/')
                if len(video_path_parts) > 2 and video_path_parts[2]:
                    self.embed_url = video_path_parts[2]
            elif parsed_embed.query:
                first_pair = parsed_embed.query.split('&')[0]
                if '=' in first_pair:
                    first_value = first_pair.split('=', 1)[1]
                    if first_value:
                        self.embed_url = first_value
        except Exception as error_parse_embed_url:
            return {
                'status': False,
                'message': str(error_parse_embed_url)
            }

        try:
            request = cffi_requests.post(
                url='https://jeniusplay.com/player/index.php',
                params={
                    "data": self.embed_url,
                    "do": "getVideo"
                },
                headers={
                    "Host": "jeniusplay.com",
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
                data={
                    "hash": self.embed_url,
                    "r": self.BASE_WEB_URL,
                },
                impersonate="chrome",
            )

            if request.status_code == 200 and request.json().get('videoSource'):
                self.m3u8_url = request.json().get('videoSource')
                self.variant_playlist = m3u8.load(self.m3u8_url)
                tmp_variant_playlist = []
                variant_index = 0
                for playlist in self.variant_playlist.playlists:
                    tmp_variant_playlist.append({
                        'bandwidth': playlist.stream_info.bandwidth,
                        'resolution': str(playlist.stream_info.resolution[0]) + 'x' + str(playlist.stream_info.resolution[1]),
                        'uri': playlist.uri,
                        'id': str(variant_index)
                    })
                    variant_index += 1
                is_variant_playlist = True if len(tmp_variant_playlist) > 1 else False
                return {
                    'status': True,
                    'm3u8_url': self.m3u8_url,
                    'variant_playlist': tmp_variant_playlist,
                    'is_variant_playlist': is_variant_playlist
                }
            else:
                return {
                    'status': False,
                    'message': 'Failed to get m3u8 URL'
                }
        except Exception as error_get_m3u8_url:
            return {
                'status': False,
                'message': str(error_get_m3u8_url)
            }

    # Characters m3u8_To_MP4 strips out of file names (helpers/path_helper.py).
    # Mirrored here so the path we hand back matches the file it actually wrote.
    WINDOWS_BANNED_CHARACTERS = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']

    @staticmethod
    def safe_file_stem(name, fallback='video'):
        """Reduce an untrusted title to one safe path component.

        video_name is parsed out of the remote page, so it must never reach
        open() or a path join unfiltered: a '/' escapes the target directory
        and a Windows-reserved character makes the write fail outright.
        """
        if not name:
            return fallback
        cleaned = str(name)
        for char in IdlixHelper.WINDOWS_BANNED_CHARACTERS:
            cleaned = cleaned.replace(char, '')
        cleaned = ''.join(char for char in cleaned if char.isprintable())
        cleaned = ' '.join(cleaned.split())
        # A component that is nothing but dots ("..", "...") is meaningless on
        # its own and is a footgun for any caller that appends no extension.
        if not cleaned or set(cleaned) == {'.'}:
            return fallback
        return cleaned

    @classmethod
    def safe_mp4_name(cls, name):
        """Same shape m3u8_To_MP4 produces, so our reported path is exact."""
        stem = cls.safe_file_stem(name)
        return stem if stem.endswith('.mp4') else stem + '.mp4'

    @staticmethod
    def unique_mp4_name(directory, wanted):
        """Pick a target name that does not exist yet.

        m3u8_To_MP4 silently swaps in a random name when the requested file is
        already there, which left us reporting a path the user could not find.
        """
        if not os.path.exists(os.path.join(directory, wanted)):
            return wanted
        stem, ext = os.path.splitext(wanted)
        counter = 1
        while True:
            candidate = '{} ({}){}'.format(stem, counter, ext)
            if not os.path.exists(os.path.join(directory, candidate)):
                return candidate
            counter += 1

    def download_m3u8(self):
        try:
            if not self.m3u8_url:
                return {
                    'status': False,
                    'message': 'M3U8 URL is required'
                }

            download_dir = os.path.join(os.getcwd(), 'downloads')
            tmp_dir = os.path.join(os.getcwd(), 'tmp')
            os.makedirs(tmp_dir, exist_ok=True)
            os.makedirs(download_dir, exist_ok=True)

            mp4_file_name = self.unique_mp4_name(
                download_dir, self.safe_mp4_name(self.video_name)
            )

            m3u8_To_MP4.multithread_download(
                m3u8_uri=self.m3u8_url,
                max_num_workers=10,
                mp4_file_name=mp4_file_name,
                mp4_file_dir=download_dir,
                tmpdir=tmp_dir
            )
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {
                'status': True,
                'message': 'Download success',
                'path': os.path.join(download_dir, mp4_file_name)
            }
        except Exception as error_download_m3u8:
            return {
                'status': False,
                'message': str(error_download_m3u8)
            }

    def get_subtitle(self, download=True):
        try:
            if not self.embed_url:
                return {
                    'status': False,
                    'message': 'Embed URL is required'
                }

            request = cffi_requests.post(
                url='https://jeniusplay.com/player/index.php',
                params={
                    "data": self.embed_url,
                    "do": "getVideo"
                },
                headers={
                    "Host": "jeniusplay.com",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
                data={
                    "hash": self.embed_url,
                    "r": self.BASE_WEB_URL
                },
                impersonate="chrome",

            )
            regex_subtitle = re.search(r"var playerjsSubtitle = \"(.*)\";", request.text)
            
            if regex_subtitle:
                subtitle_value = regex_subtitle.group(1)

                # the old code did split("https://")[1] twice, which raised
                # IndexError whenever the captured value held no https:// in it
                if "https://" in subtitle_value:
                    subtitle_url = "https://" + subtitle_value.split("https://", 1)[1]
                elif subtitle_value.startswith("http://"):
                    subtitle_url = subtitle_value
                else:
                    self.is_subtitle = False
                    return {
                        'status': False,
                        'message': 'Unparsable subtitle URL: ' + subtitle_value[:80]
                    }

                if download:
                    subtitle_request = requests.get(
                        url=subtitle_url,
                    )
                    subtitle_stem = self.safe_file_stem(self.video_name).replace(" ", "_")
                    vtt_path = subtitle_stem + '.vtt'
                    with open(vtt_path, 'wb') as subtitle_file:
                        subtitle_file.write(subtitle_request.content)
                    self.convert_vtt_to_srt(vtt_path)

                    # the os.rename(srt, srt) that used to follow was a no-op
                    self.is_subtitle = True
                    logger.success('[SUCCESS] Subtitle \'' + subtitle_stem + '\' downloaded.')
                    return {
                        'status': True,
                        'subtitle': subtitle_stem + '.srt',
                    }

                self.is_subtitle = True
                return {
                    'status': True,
                    'subtitle': subtitle_url
                }
            else:
                self.is_subtitle = False
                return {
                    'status': False,
                    'message': 'Subtitle not found'
                }
        except Exception as error_get_subtitle:
            return {
                'status': False,
                'message': str(error_get_subtitle)
            }

    @staticmethod
    def convert_vtt_to_srt(vtt_file):
        convert_file = ConvertFile(vtt_file, "utf-8")
        convert_file.convert()

    def set_m3u8_url(self, m3u8_url):
        self.m3u8_url = m3u8_url
