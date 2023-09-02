#!/usr/bin/python3
# coding: utf-8

"""
This module is to download subtitle from Friday Video
"""

import os
from pathlib import Path
import re
import shutil
import sys
import time
import orjson
from configs.config import config, credentials, user_agent
from utils.io import rename_filename, download_files
from utils.helper import get_all_languages, get_locale, get_language_code
from utils.subtitle import convert_subtitle
from services.service import Service


class Viki(Service):
    """
    Service code for Vike streaming service (https://www.viki.com/).

    Authorization: Cookies
    """

    def __init__(self, args):
        super().__init__(args)
        self._ = get_locale(__name__, self.locale)

    def movie_metadata(self, data, video_id):
        title = data['name'].strip()
        release_year = data['datePublished'][:4]

        self.logger.info("\n%s (%s)", title, release_year)

        title = rename_filename(f'{title}.{release_year}')
        folder_path = os.path.join(self.download_path, title)
        filename = f"{title}.WEB-DL.{self.platform}.vtt"

        languages = set()
        subtitles = []

        media_info = self.get_media_info(video_id=video_id, filename=filename)

        subs, lang_paths = self.get_subtitle(
            media_info=media_info, folder_path=folder_path, filename=filename)
        subtitles += subs
        languages = set.union(languages, lang_paths)

        if subtitles:
            self.logger.info(
                self._(
                    "\nDownload: %s\n---------------------------------------------------------------"),
                filename)

            self.download_subtitle(
                subtitles=subtitles, languages=languages, folder_path=folder_path)

    def series_metadata(self, data):
        content_id = re.search(
            r'(^[^\-]+)', os.path.basename(data['url']))
        content_id = content_id.group(1)

        season_index = re.search(r'(.+) Season (\d+)', data['name'])
        if season_index:
            title = season_index.group(1).strip()
            season_index = int(season_index.group(2))
        else:
            title = data['name'].strip()
            season_index = 1

        self.logger.info(self._("\n%s Season %s"), title, season_index)

        episodes_url = self.config['api']['episodes'].format(
            content_id=content_id, time=int(time.time()))

        res = self.session.get(url=episodes_url, timeout=5)

        episodes = []
        if res.ok:
            episodes = res.json()['response']
            if len(episodes) == 0:
                self.logger.error(res.text)
                sys.exit(1)
        else:
            self.logger.error(res.text)
            sys.exit(1)

        episode_num = episodes[0]['container']['planned_episodes']
        current_eps = len(episodes)
        name = rename_filename(f'{title}.S{str(season_index).zfill(2)}')
        folder_path = os.path.join(self.download_path, name)

        if self.last_episode:
            episodes = [episodes[-1]]
            self.logger.info(self._("\nSeason %s total: %s episode(s)\tdownload season %s last episode\n---------------------------------------------------------------"),
                             season_index,
                             episode_num,
                             season_index)
        else:
            if current_eps and current_eps != episode_num:
                self.logger.info(self._("\nSeason %s total: %s episode(s)\tupdate to episode %s\tdownload all episodes\n---------------------------------------------------------------"),
                                 season_index, episode_num, current_eps)
            else:
                self.logger.info(self._("\nSeason %s total: %s episode(s)\tdownload all episodes\n---------------------------------------------------------------"),
                                 season_index,
                                 episode_num)

        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)

        languages = set()
        subtitles = []
        for episode in episodes:
            episode_index = int(episode['number'])
            if not self.download_season or season_index in self.download_season:
                if not self.download_episode or episode_index in self.download_episode:
                    filename = f'{title}.S{str(season_index).zfill(2)}E{str(episode_index).zfill(2)}.WEB-DL.{self.platform}.vtt'
                    media_info = self.get_media_info(
                        video_id=episode['id'], filename=filename)
                    subs, lang_paths = self.get_subtitle(
                        media_info=media_info, folder_path=folder_path, filename=filename)
                    if not subs:
                        break
                    subtitles += subs
                    languages = set.union(languages, lang_paths)

        self.download_subtitle(
            subtitles=subtitles, languages=languages, folder_path=folder_path)

    def get_media_info(self, video_id, filename):
        self.session.headers.update({
            'x-viki-app-ver': self.config['vmplayer']['version'],
            'x-client-user-agent': user_agent,
            'x-viki-as-id': self.cookies['session__id'],
            'x-viki-device-id': self.cookies['device_id']
        })
        media_info_url = self.config['api']['videos'].format(
            video_id=video_id)

        res = self.session.get(url=media_info_url, timeout=5)

        if res.ok:
            if 'Too Many Requests' in res.text:
                self.logger.debug(res.text)
                self.logger.info(
                    "\nToo Many Requests! Login access token (%s) is expired!\nPlease re-download cookies")
                os.remove(
                    Path(config.directories['cookies']) / credentials[self.platform]['cookies'])
                sys.exit(1)
            else:
                data = res.json()
                if 'video' in data:
                    self.logger.debug("media_info: %s", data)
                    return data
                else:
                    self.logger.error("%s\nError: %s\n", os.path.basename(
                        filename), data['error'])
        else:
            self.logger.error(res.text)
            sys.exit(1)

    def get_subtitle(self, media_info, folder_path, filename):

        lang_paths = set()
        subtitles = []
        available_languages = set()

        if media_info:
            if 'subtitles' in media_info and media_info['subtitles']:
                for sub in media_info['subtitles']:
                    if sub['percentage'] == 100:
                        sub_lang = get_language_code(sub['srclang'])
                        available_languages.add(sub_lang)
                        if sub_lang in self.subtitle_language:
                            if len(lang_paths) > 1:
                                lang_folder_path = os.path.join(
                                    folder_path, sub_lang)
                            else:
                                lang_folder_path = folder_path
                            lang_paths.add(lang_folder_path)

                            os.makedirs(lang_folder_path,
                                        exist_ok=True)

                            subtitles.append({
                                'name': filename.replace('.vtt', f'.{sub_lang}.vtt'),
                                'path': lang_folder_path,
                                'url': sub['src']
                            })
                get_all_languages(available_languages=available_languages,
                                  subtitle_language=self.subtitle_language, locale_=self.locale)
            elif media_info['video']['hardsubs']:
                self.logger.error(
                    self._("\nSorry, there's no embedded subtitles in this video!"))
            else:
                self.logger.error(
                    self._("\nPlease check your subscription plan, and make sure you are able to watch it online!"))

        return subtitles, lang_paths

    def download_subtitle(self, subtitles, folder_path, languages=None):
        if subtitles:
            download_files(subtitles)
            if languages:
                for lang_path in sorted(languages):
                    convert_subtitle(
                        folder_path=lang_path, subtitle_format=self.subtitle_format, locale=self.locale)
            convert_subtitle(folder_path=folder_path,
                             platform=self.platform, subtitle_format=self.subtitle_format, locale=self.locale)

    def main(self):
        res = self.session.get(url=self.url, timeout=5)

        if res.ok:
            match = re.search(r'(\{"@context":.+\}\})', res.text)
            data = orjson.loads(match.group(1))
            if '/movies' in self.url:
                match = re.search(r'({\"props\":{.*})', res.text)
                video_id = orjson.loads(match.group(1))[
                    'props']['pageProps']['containerJson']['watch_now']['id']
                self.movie_metadata(data, video_id)
            else:
                self.series_metadata(data)
        else:
            self.logger.error(res.text)
