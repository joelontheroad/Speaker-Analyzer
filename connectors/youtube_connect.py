# **********************************************************
# Public Meeting Speaker Analyzer
# file: connectors/youtube_connect.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import yt_dlp
import re

class YoutubeConnector:
    DISPLAY_NAME = "YouTube General Analysis"
    SLUG = "YouTube"
    
    def __init__(self, logger, config):
        self.log = logger
        self.config = config

    @staticmethod
    def can_handle(url):
        # Acts as default/generic connector for now, or specific to YT
        return "youtube.com" in url or "youtu.be" in url

    def get_metadata(self, url):
        self.log.info(f"Fetching YouTube metadata for {url}...")
        try:
            ydl_opts = {'quiet': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                offset = 0
                # Check chapters for Public Comment if any
                if 'chapters' in info and info['chapters']:
                    for chap in info['chapters']:
                        if re.search(r"Public\s*Com", chap.get('title', ''), re.I):
                            offset = int(chap.get('start_time', 0))
                            self.log.info(f"Found YouTube Chapter '{chap['title']}' at {offset}s")
                            break
                            
                return {
                    "title": info.get('title'),
                    "date": info.get('upload_date'),
                    "offset": offset,
                    "media_url": url, # For YouTube, the source URL is the media URL for yt-dlp
                    "source_url": url
                }
        except Exception as e:
            self.log.error(f"YouTube metadata extraction failed: {e}")
            return None
