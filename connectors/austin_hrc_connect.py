# **********************************************************
# Public Meeting Speaker Analyzer
# file: connectors/austin_hrc_connect.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import re
import json
import urllib.request
from datetime import datetime

class AustinHRCConnector:
    DISPLAY_NAME = "Austin Human Rights Commission"
    SLUG = "AustinHRC"
    
    def __init__(self, logger, config_or_fm):
        self.log = logger
        # Some connectors take config, some take file_manager
        self.config = config_or_fm

    @staticmethod
    def can_handle(url):
        return "austintexas.box.com/s/" in url or "austintexas.app.box.com/s/" in url

    def get_metadata(self, url):
        try:
            # 1. Get the direct download URL from the Box page
            media_url = self._get_box_direct_url(url)
            if not media_url:
                self.log.error(f"Could not extract direct media URL from Box link: {url}")
                return None
            
            # 2. Get the meeting date from the Austin HRC index pages
            date_str = self._find_meeting_date(url)
            
            return {
                "title": "Austin Human Rights Commission",
                "date": date_str,
                "offset": 0,
                "media_url": media_url,
                "source_url": url
            }
        except Exception as e:
            self.log.error(f"Austin HRC Metadata extraction failed: {e}")
            return None

    def _get_box_direct_url(self, url):
        """Extracts the direct MP3 download URL from the Box shared link."""
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8', errors='ignore')
            
            match = re.search(r'Box\.postStreamData = ({.*?});', html)
            if match:
                data = json.loads(match.group(1))
                for key, value in data.items():
                    if '/item/f_' in key:
                        items = value.get('items', [])
                        for item in items:
                            file_id = item.get('id')
                            if file_id:
                                shared_name = url.rstrip('/').split('/')[-1]
                                dl_url = f"https://austintexas.app.box.com/index.php?rm=box_download_shared_file&shared_name={shared_name}&file_id=f_{file_id}"
                                return dl_url
        except Exception as e:
            self.log.error(f"Error fetching Box page {url}: {e}")
        return None

    def _find_meeting_date(self, box_url):
        """Cross-references the Box URL against the Austin HRC index to find the date."""
        base_url = "https://www.austintexas.gov/cityclerk/boards_commissions/meetings/"
        
        # Determine the shared block (e.g., am98w4w94ps80lazx9k1tf65j3bw0045)
        # Some links use austintexas.box.com, others use austintexas.app.box.com
        shared_name_match = re.search(r'/s/([a-zA-Z0-9]+)', box_url)
        if not shared_name_match:
            return None
            
        shared_name = shared_name_match.group(1)
        
        # Check current year and a few previous years
        current_year = datetime.now().year
        pages_to_check = [f"{year}_33_1.htm" for year in range(current_year, current_year - 4, -1)]
        pages_to_check.insert(0, "33_1.htm") # Main index

        date_pattern = re.compile(r'<div class="bcic_mtgdate">(.*?)</div>', re.IGNORECASE)
        
        for page in pages_to_check:
            url = base_url + page
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    html = response.read().decode('utf-8', errors='ignore')
                    
                    chunks = html.split('<div class="bcic_mtgdate">')
                    for chunk in chunks[1:]:
                        date_str_end = chunk.find('</div>')
                        if date_str_end == -1:
                            continue
                        date_str_raw = chunk[:date_str_end].strip()
                        date_str_clean = re.sub(r'\(.*?\)', '', date_str_raw).strip()
                        
                        # Check if this chunk contains the shared link
                        if shared_name in chunk:
                            return date_str_clean
            except Exception as e:
                # Page might not exist, that's fine
                self.log.debug(f"Error checking {url} for date: {e}")
                
        return None
