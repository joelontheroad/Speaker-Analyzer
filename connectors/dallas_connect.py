# **********************************************************
# Public Meeting Speaker Analyzer
# file: connectors/dallas_connect.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import re
import requests
from bs4 import BeautifulSoup

class DallasConnector:
    DISPLAY_NAME = "Dallas City Council Meeting Public Speakers"
    SLUG = "Dallas"
    
    def __init__(self, logger, config):
        self.log = logger
        self.config = config

    @staticmethod
    def can_handle(url):
        return "dallastx.new.swagit.com" in url

    def get_metadata(self, url):
        self.log.info(f"DallasConnector extracting metadata for {url}")
        try:
            # We use a URL query parameter `?segment=N` to spoof multiple logical meetings
            # for a single physical Dallas City Council Meeting video.
            segment_match = re.search(r'\?segment=(\d+)', url)
            target_segment = int(segment_match.group(1)) if segment_match else 1
            
            # Base URL without the query parameter for fetching
            base_url = url.split('?')[0] if '?' in url else url

            # To avoid doing the HTTP request multiple times if speaker-analyzer calls this
            # in a loop with spoofed URLs, we could cache the page, but for now we just fetch.
            response = requests.get(base_url, timeout=10)
            if response.status_code != 200:
                self.log.error(f"Failed to access Dallas Swagit page: HTTP {response.status_code} for {url}")
                return None
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract basic metadata
            title_tag = soup.find('title')
            base_title = title_tag.text.split('|')[0].strip() if title_tag else "Dallas City Council Meeting"
            
            date_str = None
            date_element = soup.find(class_='video-date')
            if date_element:
                date_str = date_element.text.strip()
            
            # Fallback: Try to find a date in the title if the video-date tag is missing
            if not date_str or date_str.lower() == 'unknown date':
                date_match = re.search(r'([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})', base_title)
                if date_match:
                    date_str = date_match.group(1)
                    self.log.info(f"Date found in title fallback: {date_str}")
                else:
                    date_str = None
            
            media_url = self.extract_media_url(soup)
            
            # Determine meeting type to apply correct extraction logic
            is_briefing = "briefing" in base_title.lower()
            
            if is_briefing:
                offset, duration = self._scrape_briefing_agenda(soup)
                
                return {
                    "title": base_title,
                    "date": date_str,
                    "offset": offset or 0,
                    "duration": duration or 0,
                    "media_url": media_url,
                    "source_url": base_url # Return base URL so the video ID matches cleanly, or keep url?
                }
            else:
                # City Council Agenda Meeting
                segments = self._scrape_agenda_meeting(soup)
                
                if not segments:
                    return {
                        "title": base_title,
                        "date": date_str,
                        "offset": 0,
                        "duration": 0,
                        "media_url": media_url,
                        "source_url": base_url
                    }
                
                # We have segments. Return the specific one requested via `?segment=N`
                # Segments array is 0-indexed, segments parameter is 1-indexed.
                idx = target_segment - 1
                if idx < 0 or idx >= len(segments):
                    self.log.warning(f"Requested segment {target_segment} is out of bounds for {len(segments)} segments. Defaulting to first.")
                    idx = 0
                    
                offset, duration = segments[idx]
                segment_title = f"{base_title} - segment {target_segment} of {len(segments)}"
                
                return {
                    "title": segment_title,
                    "date": date_str,
                    "offset": offset,
                    "duration": duration,
                    "media_url": media_url,
                    "source_url": url # Keep spoofed URL to differentiate in manifest
                }
                
        except Exception as e:
            self.log.error(f"Dallas Metadata scrape failed: {e}")
            return None

    def _scrape_briefing_agenda(self, soup):
        offset = 0
        duration = 0
        items = soup.select('#video-index-sm .playerControl[data-title]')
        if not items:
            self.log.warning("No agenda items found for Dallas Council Briefing.")
            return offset, duration

        for i, item in enumerate(items):
            title = item.get('data-title', '').strip().upper()
            if "OPEN MICROPHONE SPEAKERS" in title:
                try:
                    start_ts = int(item.get('data-ts', 0))
                    # Duration is start time of NEXT item minus start time of THIS item
                    if i + 1 < len(items):
                        end_ts = int(items[i+1].get('data-ts', start_ts))
                    else:
                        end_ts = start_ts
                    
                    offset = start_ts
                    duration = end_ts - start_ts if end_ts > start_ts else 0
                    self.log.info(f"Found Briefing Open Microphone: offset={offset}s, duration={duration}s")
                    break
                except (ValueError, TypeError) as e:
                    self.log.error(f"Error parsing Dallas Briefing timestamps: {e}")
                    
        return offset, duration

    def _scrape_agenda_meeting(self, soup):
        # Returns a list of tuples: [(offset_1, duration_1), (offset_2, duration_2), ...]
        segments = []
        items = soup.select('#video-index-sm .playerControl[data-title]')
        if not items:
            self.log.warning("No agenda items found for Dallas Agenda Meeting.")
            return segments

        # Iterate through items to find all unique "OPEN MICROPHONE" segments
        unique_open_mics = []
        for i, item in enumerate(items):
            title = item.get('data-title', '').strip().upper()
            if "OPEN MICROPHONE" in title:
                start_ts = int(item.get('data-ts', 0))
                # Avoid exact duplicates (Swagit DOM sometimes repeats identical anchor and span tags)
                if not any(om_start == start_ts for om_start, _, _ in unique_open_mics):
                    unique_open_mics.append((start_ts, item, i))

        # We expect up to 2 segments (Part 1 and Part 2). Process the first one as Part 1, the last as Part 2.
        if len(unique_open_mics) > 0:
            # First segment (Part 1)
            start_ts, item, idx = unique_open_mics[0]
            # Find the next item with a different timestamp to determine duration
            end_ts = start_ts
            for j in range(idx + 1, len(items)):
                next_ts = int(items[j].get('data-ts', 0))
                if next_ts > start_ts:
                    end_ts = next_ts
                    break
            
            duration1 = end_ts - start_ts if end_ts > start_ts else 0
            segments.append((start_ts, duration1))
            self.log.info(f"Found Agenda Meeting Part 1: offset={start_ts}s, duration={duration1}s")

        if len(unique_open_mics) > 1:
            # Last segment (Part 2) 
            # (Note: if there are somehow >2, we just take the last one as Part 2 per design doc)
            start_ts, item, idx = unique_open_mics[-1]
            
            # Use data-end-ts if valid, otherwise find highest data-ts in all items, or default to 0
            end_ts_raw = item.get('data-end-ts')
            if end_ts_raw and int(end_ts_raw) > start_ts:
                end_ts = int(end_ts_raw)
            else:
                all_end_ts = [int(x.get('data-end-ts', 0)) for x in items if x.get('data-end-ts')]
                if all_end_ts:
                    end_ts = max(all_end_ts)
                else:
                    all_ts = [int(x.get('data-ts', 0)) for x in items]
                    end_ts = max(all_ts) if all_ts else start_ts

            duration2 = end_ts - start_ts if end_ts > start_ts else 0
            segments.append((start_ts, duration2))
            self.log.info(f"Found Agenda Meeting Part 2: offset={start_ts}s, duration={duration2}s")

        return segments

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
