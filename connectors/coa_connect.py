# **********************************************************
# Public Meeting Speaker Analyzer
# file: connectors/coa_connect.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import re
import requests
from bs4 import BeautifulSoup

class COAConnector:
    DISPLAY_NAME = "Austin City Council Meeting Public Comments"
    SLUG = "Austin"
    
    def __init__(self, logger, config):
        self.log = logger
        self.config = config

    @staticmethod
    def can_handle(url):
        return "austintexas.gov" in url or "swagit.com" in url

    def get_metadata(self, url):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                self.log.error(f"Failed to access Swagit page: HTTP {response.status_code} for {url}")
                return None
                
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.find('title').text.split('|')[0].strip()
            
            date_str = None
            date_element = soup.find(class_='video-date')
            if date_element:
                date_str = date_element.text.strip()
            
            # Fallback: Try to find a date in the title if the video-date tag is missing
            if not date_str or date_str.lower() == 'unknown date':
                # Looking for patterns like "Oct 19, 2023" or "October 19, 2023"
                date_match = re.search(r'([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})', title)
                if date_match:
                    date_str = date_match.group(1)
                    self.log.info(f"Date found in title fallback: {date_str}")
                else:
                    date_str = None # Fail hard
            
            offset = self.get_chapter_data(soup)
            if offset == 0:
                 for link in soup.find_all('a', string=re.compile("Public Communication", re.I)):
                    match = re.search(r'playAt\((\d+)\)', link.get('onclick', ''))
                    if match:
                        offset = int(match.group(1))
                        self.log.info(f"Precision match found at {offset}s")
                        break

            media_url = self.extract_media_url(soup)
            
            return {
                "title": title,
                "date": date_str,
                "offset": offset,
                "media_url": media_url,
                "source_url": url
            }
        except Exception as e:
            self.log.error(f"COA Metadata scrape failed: {e}")
            return None

    def extract_media_url(self, soup):
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Priority 1: m3u8 playlist (Best for yt-dlp)
                if ".m3u8" in script.string:
                     match = re.search(r'(https?://[^"\']+\.m3u8)', script.string)
                     if match: return match.group(1)
                
                # Priority 2: Direct MP4
                if ".mp4" in script.string:
                    match = re.search(r'(https?://[^"\']+\.mp4)', script.string)
                    if match: return match.group(1)
        return None

    def get_chapter_data(self, soup):
        candidate_ts = 0
        
        # Iterate ALL links to find the best match
        # Priority: "Public Communication" > "Public Comment"
        for link in soup.find_all('a'):
            txt = link.get_text(strip=True)
            href = link.get('href', '')
            onclick = link.get('onclick', '')
            
            ts = 0
            # Extract TS from href or onclick
            match_href = re.search(r'play/\d+/(\d+)', href)
            match_onclick = re.search(r'playAt\((\d+)\)', onclick)
            
            if match_href:
                ts = int(match_href.group(1))
            elif match_onclick:
                ts = int(match_onclick.group(1))
            
            if ts > 0:
                if "Public Communication" in txt:
                    self.log.info(f"Found PRIMARY target chapter: '{txt}' at {ts}s")
                    return ts
                elif "Public Comment" in txt and candidate_ts == 0:
                     self.log.info(f"Found SECONDARY target chapter: '{txt}' at {ts}s")
                     candidate_ts = ts
        
        if candidate_ts > 0:
            return candidate_ts
            
        # Fallback to table row approach
        rows = soup.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 2: continue
            
            timestamp_text = cells[0].get_text(strip=True)
            chapter_title = cells[1].get_text(strip=True)
            
            if "Public Comment" in chapter_title or "Public Communication: General" in chapter_title:
                self.log.info(f"Found target chapter (table): '{chapter_title}' at {timestamp_text}")
                return self._time_to_seconds(timestamp_text)
                
        return 0

    def _time_to_seconds(self, t_str):
        parts = list(map(int, t_str.split(':')))
        if len(parts) == 2: return parts[0] * 60 + parts[1]
        if len(parts) == 3: return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return 0
