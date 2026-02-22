# **********************************************************
# Public Meeting Speaker Analyzer
# file: connectors/houston_connect.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import re
import requests
from bs4 import BeautifulSoup

class HoustonConnector:
    DISPLAY_NAME = "Houston City Council Meeting Public Speakers"
    SLUG = "Houston"
    
    def __init__(self, logger, config):
        self.log = logger
        self.config = config

    @staticmethod
    def can_handle(url):
        return "houstontx.new.swagit.com" in url

    def get_metadata(self, url):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                self.log.error(f"Failed to access Houston Swagit page: HTTP {response.status_code} for {url}")
                return None
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract basic metadata
            title_tag = soup.find('title')
            title = title_tag.text.split('|')[0].strip() if title_tag else "Houston City Council Meeting"
            
            date_element = soup.find(class_='video-date')
            date_str = date_element.text.strip() if date_element else "Unknown Date"
            
            offset, duration = self._scrape_agenda(soup)
            
            media_url = self.extract_media_url(soup)
            
            return {
                "title": title,
                "date": date_str,
                "offset": offset,
                "duration": duration,
                "media_url": media_url,
                "source_url": url
            }
        except Exception as e:
            self.log.error(f"Houston Metadata scrape failed: {e}")
            return None

    def _scrape_agenda(self, soup):
        """
        Scrapes the agenda to find 'PUBLIC SPEAKERS' and calculates duration.
        """
        offset = 0
        duration = 0
        
        # Agenda items are in #video-index-sm .playerControl[data-title]
        items = soup.select('#video-index-sm .playerControl[data-title]')
        
        if not items:
            self.log.warning("No agenda items found for Houston meeting.")
            return offset, duration

        for i, item in enumerate(items):
            title = item.get('data-title', '').strip().upper()
            if "PUBLIC SPEAKERS" in title:
                try:
                    start_ts = int(item.get('data-ts', 0))
                    # Prefer data-end-ts if it exists and is valid
                    end_ts_raw = item.get('data-end-ts')
                    if end_ts_raw and int(end_ts_raw) > start_ts:
                        end_ts = int(end_ts_raw)
                    elif i + 1 < len(items):
                         # Fallback: next item's start time
                         end_ts = int(items[i+1].get('data-ts', start_ts))
                    else:
                        end_ts = start_ts # Will fall back to default duration
                    
                    offset = start_ts
                    if end_ts > start_ts:
                        duration = end_ts - start_ts
                    
                    self.log.info(f"Found Houston Public Speakers: offset={offset}s, duration={duration}s")
                    break
                except (ValueError, TypeError) as e:
                    self.log.error(f"Error parsing Houston timestamps: {e}")
                    
        return offset, duration

    def extract_media_url(self, soup):
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Priority 1: m3u8 playlist
                if ".m3u8" in script.string:
                     match = re.search(r'(https?://[^"\']+\.m3u8)', script.string)
                     if match: return match.group(1)
                
                # Priority 2: Direct MP4
                if ".mp4" in script.string:
                    match = re.search(r'(https?://[^"\']+\.mp4)', script.string)
                    if match: return match.group(1)
        return None
