# **********************************************************
# Public Meeting Speaker Analyzer
# file: utils/analyzer.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import os, json, requests, yaml, hashlib, re, sys
from datetime import datetime

class Analyzer:
    def __init__(self, logger, file_manager):
        self.log = logger
        self.fm = file_manager
        self.prompts = self._load_prompts()
        self.api_url = self.fm.get_network_setting('llm_api_url')
        if not self.api_url: self.api_url = "http://127.0.0.1:1234"
        
        # Spinner infrastructure
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0
        
        # Define organization categories for the Executive Briefing
        self.org_categories = [
            "Advocacy & Human Rights Groups",
            "Religious & Faith Institutions",
            "Academic & Student Organizations",
            "Political & Policy Organizations",
            "Professional & Labor Associations",
            "Unaffiliated / Private Citizens"
        ]

    def _load_prompts(self):
        return self.fm.load_yaml("configs/prompts.yaml")

    def _get_topic(self):
        prompt_text = self.prompts.get('analysis_instructions', '')
        if not prompt_text:
            return "General Analysis"
        topic_match = re.search(r'Topic:\s*"?([^"]+)"?', prompt_text, re.IGNORECASE)
        if topic_match:
            return topic_match.group(1).strip()
        return prompt_text.strip()

    def _get_spinner(self):
        char = self.spinner_chars[self.spinner_idx % len(self.spinner_chars)]
        self.spinner_idx += 1
        return char

    def _get_llm_config(self):
        """Get LLM configuration from defaults.yaml"""
        config = self.fm.load_yaml("configs/defaults.yaml")
        return config.get('ai_settings', {}).get('llm', {})

    def _spinner_update(self, message):
        """Update spinner animation"""
        sys.stdout.write(f"\r[{self._get_spinner()}] {message}")
        sys.stdout.flush()

    def _spinner_done(self):
        """Clear spinner line"""
        print()

    def _mask_name(self, name):
        # One-way hash for privacy
        return "Speaker_" + hashlib.sha256(name.encode()).hexdigest()[:8]
    
    def _extract_speaker_identity(self, speaker_id, text):
        """Extract speaker name and affiliation if they self-identify in their opening statement"""
        llm_config = self._get_llm_config()
        limit = llm_config.get('max_input_tokens', {}).get('identity', 2500)
        
        # Check first N characters to catch late introductions
        opening = text[:limit]
        
        # Quick check - if no common self-ID patterns, skip LLM call
        patterns = ['my name', "i'm ", "i am ", 'this is', 'speaking for', 'i represent', 'i belong to', 'member of', 'founder of', 'director of', 'volunteer with']
        if not any(pattern in opening.lower() for pattern in patterns):
            # self.log.debug(f"No identity patterns found for {speaker_id}") # Too verbose?
            return {'name': speaker_id, 'affiliation': ''}
        
        system_prompt = """Extract the speaker's Name and Affiliation from their self-identification.
        
Common patterns:
- "My name is John Smith, director of..."
- "I represent the Austin Justice Coalition"
- "I am a member of..."

Return in this EXACT format:
Name: [Full Name or NONE]
Affiliation: [Organization or NONE]

Do not invent affiliations. If they say "I am a mother", that is not an organization. Look for formal groups, titles, or collective bodies."""

        user_prompt = f"Opening statement: {opening}\n\nExtract:"
        
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            # Use configured temperature (default 0.1)
            "temperature": llm_config.get('temperature', {}).get('extraction', 0.1),
            # Use configured max tokens (default 100)
            "max_tokens": llm_config.get('max_output_tokens', {}).get('identity', 100)
            # Removed response_format: json_object to avoid compatibility issues
        }
        
        try:
            url = f"{self.api_url.rstrip('/')}/v1/chat/completions"
            resp = requests.post(url, json=payload, timeout=60)
            
            if resp.status_code == 200:
                resp_json = resp.json()
                content = resp_json['choices'][0]['message']['content'].strip()
                self.log.info(f"Identity raw output for {speaker_id}: {content}")
                
                # Parse text format
                name_match = re.search(r'Name:\s*(.+)', content, re.IGNORECASE)
                affil_match = re.search(r'Affiliation:\s*(.+)', content, re.IGNORECASE)
                
                extracted_name = name_match.group(1).strip() if name_match else 'NONE'
                affiliation = affil_match.group(1).strip() if affil_match else ''
                
                if extracted_name == 'NONE' or extracted_name == '[Full Name or NONE]':
                    extracted_name = speaker_id
                
                # Cleanup affiliation
                if not affiliation or affiliation.upper() == 'NONE' or affiliation == '[Organization or NONE]':
                    affiliation = 'NONE'
                
                # Validate name
                final_name = speaker_id
                if extracted_name and extracted_name != speaker_id and len(extracted_name) > 3:
                     # Basic validation - should look like a name (at least one letter)
                     if any(char.isalpha() for char in extracted_name):
                         final_name = extracted_name
                
                if final_name != speaker_id or affiliation.upper() != 'NONE':
                    self.log.info(f"Identity found for {speaker_id}: {final_name} | {affiliation}")
                
                return {'name': final_name, 'affiliation': affiliation}
            else:
                self.log.error(f"Identity extraction failed: Status {resp.status_code}")
                return {'name': speaker_id, 'affiliation': 'NONE'}
        except Exception as e:
            self.log.error(f"Identity extraction exception: {e}")
            return {'name': speaker_id, 'affiliation': 'NONE'}

    def _identify_presiding_officer(self, transcript_data):
        """Identify the Mayor/Chair/Presiding Officer from the meeting start"""
        segments = transcript_data.get('segments', [])
        # Sample the first 5 minutes (or first 20 segments)
        opening_text = ""
        for i, seg in enumerate(segments[:20]):
            text = seg.get('text', '')
            spk = seg.get('speaker', 'Unknown')
            opening_text += f"{spk}: {text}\n"
        
        if not opening_text:
            return None

        system_prompt = """Identify the Presiding Officer (Mayor, Chair, or President) of this meeting.
Look for phrases like:
- "Call the meeting to order"
- "I'm Mayor [Name]"
- "We're here for the [Date] meeting"

Return in this EXACT format:
SpeakerID: [The raw ID, e.g. SPEAKER_01]
Name: [Full Name]
Role: [Mayor/Chair/etc]

If you cannot identify the person, return 'NONE'."""

        user_prompt = f"Meeting Opening:\n{opening_text}\n\nIdentify:"
        
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 50
        }
        
        try:
            url = f"{self.api_url.rstrip('/')}/v1/chat/completions"
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content'].strip()
                if "NONE" in content.upper():
                    return None
                    
                spk_id_match = re.search(r'SpeakerID:\s*(\w+)', content, re.IGNORECASE)
                name_match = re.search(r'Name:\s*(.+)', content, re.IGNORECASE)
                role_match = re.search(r'Role:\s*(.+)', content, re.IGNORECASE)
                
                if spk_id_match and name_match:
                    spk_id = spk_id_match.group(1).strip()
                    name = name_match.group(1).strip()
                    role = role_match.group(1).strip() if role_match else "Presiding Officer"
                    return {"id": spk_id, "name": f"{role} {name}"}
        except Exception as e:
            self.log.error(f"Presiding officer identification error: {e}")
            
        return None

    def run_analysis(self, transcript_path, mask=False, file_index=None, total_files=None):
        video_id = os.path.basename(transcript_path).split('_transcript')[0]
        # self.log.info(f"Phase 3: Analyzing {video_id}...") # Redundant with spinner
        
        # Load Transcript
        with open(transcript_path, 'r') as f:
            data = json.load(f)

        # Load Metadata
        meta_path = os.path.join(self.fm.resolve_path('summaries'), f"{video_id}_metadata.json")
        metadata = {}
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                metadata = json.load(f)
        
        # Extract date - try from metadata first, then parse from title
        meeting_date = metadata.get('date', 'Unknown Date')
        if meeting_date == 'Unknown Date':
            title = metadata.get('title', '')
            # Try to extract date from title like "Mar 21, 2024 City Council Meetings"
            import re
            date_match = re.search(r'([A-Za-z]{3,}\.?\s+\d{1,2},\s+\d{4})', title)
            if date_match:
                meeting_date = date_match.group(1)
        
        source_url = metadata.get('source_url', '')
        
        # Get offset - this is where the audio extraction started in the video (in seconds)
        # Transcript timestamps are relative to audio start, not video start
        offset = metadata.get('offset', 0)

        # Group by speaker
        speaker_text = {}
        speaker_starts = {} # Track start time for linking
        segments = data.get('segments', [])
        
        for seg in segments:
            speaker = seg.get('speaker', 'Unknown')
            if mask and speaker != 'Unknown':
                speaker = self._mask_name(speaker)
            
            if speaker not in speaker_text:
                speaker_text[speaker] = []
                speaker_starts[speaker] = seg.get('start', 0)
            
            speaker_text[speaker].append(seg.get('text', '').strip())

        # Identify Speakers
        speaker_names = {}
        speaker_affiliations = {}
        speaker_real_names = {}
        
        for speaker_id in speaker_text:
            # Get full text for this speaker to check for self-ID
            full_text = " ".join(speaker_text[speaker_id])
            
            # Skip short utterances for name extraction to save API calls
            if len(full_text) < 50:
                speaker_names[speaker_id] = speaker_id
                speaker_affiliations[speaker_id] = "NONE"
                speaker_real_names[speaker_id] = speaker_id
                continue
                
            identity = self._extract_speaker_identity(speaker_id, full_text)
            extracted_name = identity['name']
            speaker_real_names[speaker_id] = extracted_name if extracted_name != speaker_id else speaker_id
            
            # Apply masking if requested
            if mask and extracted_name != speaker_id:  # Only mask real names, not SPEAKER_00
                speaker_names[speaker_id] = self._mask_name(extracted_name)
                # Should we mask affiliation? Usually organizations are public.
                # Let's keep affiliation unmasked unless user requested otherwise (not specified).
                speaker_affiliations[speaker_id] = identity['affiliation']
            else:
                speaker_names[speaker_id] = extracted_name
                speaker_affiliations[speaker_id] = identity['affiliation']

        results = []
        total_speakers = len(speaker_text)
        current = 0
        total_speakers_all_topics = total_speakers
        
        # Determine prefix for spinner
        file_progress = f"[{file_index} of {total_files}] " if file_index and total_files else ""
        
        # --- Presiding Officer Linkage ---
        # Even if they aren't relevant to the topic, we want them in the manifest for RAG
        presiding_officer = self._identify_presiding_officer(data)
        if presiding_officer:
            po_id = presiding_officer['id']
            po_name = presiding_officer['name']
            po_real_name = po_name
            
            # Check if this speaker is already in results (meaning they were relevant)
            # If not, add a metadata-only entry to ensure they get indexed in RAG
            already_there = any(r['internal_id'] == po_id for r in results)
            if not already_there:
                # Apply masking if requested
                if mask:
                    po_name = self._mask_name(po_name)
                
                # Use the meeting title from metadata
                meeting_title = metadata.get('title', f"{meeting_date} {video_id}")
                
                results.append({
                    "internal_id": po_id,
                    "speaker": po_name,
                    "real_name": po_real_name,
                    "affiliation": "Presiding Officer",
                    "sentiment": "Neutral",
                    "example": "Meeting Presiding Officer.", # Renamed from 'summary' to 'example' to match existing structure
                    "meeting": meeting_title,
                    "date": meeting_date,
                    "start_time": offset, # Start of their duty
                    "original_video": source_url, # Original URL without timestamp
                    "video_url": source_url, # Original URL
                    "summary_file": os.path.basename(transcript_path),
                    "metadata_only": True # Flag to filter out of visible reports
                })

        for speaker in speaker_text:
            texts = speaker_text[speaker]
            full_text = " ".join(texts)
            if len(full_text) < 50: continue 
            
            current += 1
            # Show meeting name in spinner (title already includes date)
            meeting_title = metadata.get('title', f"{meeting_date} {video_id}")
            self._spinner_update(f"{file_progress}Analyzing speaker {current}/{total_speakers} in {meeting_title}")

            # Check relevance first - skip if not relevant to topic
            is_relevant = self._check_relevance(speaker, full_text)
            if not is_relevant:
                continue

            # Resolve display name BEFORE generating summary so the LLM only sees the masked name
            display_name = speaker_names[speaker]
            affiliation = speaker_affiliations.get(speaker, "")
            real_name = speaker_real_names.get(speaker, display_name)

            # Pass 1: Sentiment classification (low temperature)
            sentiment = self._analyze_sentiment(display_name, full_text)
            
            # Pass 2: Generate summary - pass display_name and real_name to ensure scrubbing
            summary = self._generate_summary(display_name, full_text, mask=mask, real_name=real_name)
            
            # Create Deep Link to Video with timestamp
            start_time = int(speaker_starts[speaker])
            # Add offset - audio timestamps are relative to extraction start, not video start
            video_timestamp = start_time + offset
            
            # Use proper Swagit format: remove trailing /0 and use ?ts= query param
            base_url = source_url.split('?')[0].split('#')[0].rstrip('/')
            if base_url.endswith('/0'):
                base_url = base_url[:-2]  # Remove /0
            
            # Format timestamp depending on source
            if 'box.com' in base_url:
                video_link = f"{base_url}?t={video_timestamp}s"
            else:
                video_link = f"{base_url}?ts={video_timestamp}"
            
            # Store both for report
            video_url_original = source_url

            results.append({
                "internal_id": speaker,    # Raw ID from WhisperX (e.g. SPEAKER_01)
                "speaker": display_name,  # Use extracted/masked name
                "real_name": real_name,   # Preserve real name for semantic analyzer/RAG
                "affiliation": affiliation,
                "sentiment": sentiment,
                "example": summary,
                "meeting": f"{metadata.get('title', video_id)} ({meeting_date})",
                "summary_file": os.path.basename(transcript_path),
                "original_video": video_link,  # Full URL with timestamp
                "video_url": source_url,  # Original URL
                "date": meeting_date,
                "start_time": start_time
            })
        
        
        self._spinner_done()
        
        # Return tuple: (results, total_speakers_in_this_file, meeting_date, meeting_title)
        return results, total_speakers_all_topics, meeting_date, metadata.get('title', video_id)

    def _analyze_sentiment(self, speaker, text):
        # Strict sentiment classification
        # Note: We use the topic/keywords from prompts.yaml for context,
        # but override the verbose analysis_instructions with a strict format.
        
        # Strict sentiment classification using user-defined yaml parameters
        llm_config = self._get_llm_config()
        limit = llm_config.get('max_input_tokens', {}).get('sentiment', 12000)

        keywords_list = self.prompts.get('keywords', [])
        keywords_str = ", ".join(map(str, keywords_list)) if isinstance(keywords_list, list) else str(keywords_list)
        
        # Load dynamic user instructions
        topic = self._get_topic()
        sentiment_instructions = self.prompts.get('sentiment_instructions', '')
        categories = self.prompts.get('sentiment_categories', ['Neutral'])
        categories_str = ", ".join(categories)
        
        system_prompt = f"""You are analyzing public comment sentiment.

Analysis Instructions / Topic:
{topic}

Keywords for context: {keywords_str}

{sentiment_instructions}

Respond with ONLY these exact labels: {categories_str}."""

        payload_text = text[:limit]
        self.log.info(f"Sentiment Analysis: Sending {len(payload_text)} chars to LLM for speaker '{speaker}' (Limit: {limit})")

        user_prompt = f"Speaker: {speaker}\n\nStatement: {payload_text}\n\nSentiment:"

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 10
        }
        
        try:
            url = f"{self.api_url.rstrip('/')}/v1/chat/completions"
            if hasattr(self.log, 'debug'):
                self.log.debug(f"LLM Request URL: {url}")
                self.log.debug(f"LLM Payload: {payload}")
            
            resp = requests.post(url, json=payload, timeout=120)
            
            if hasattr(self.log, 'debug'):
                self.log.debug(f"LLM Response Status: {resp.status_code}")
            
            if resp.status_code == 200:
                resp_json = resp.json()
                
                if hasattr(self.log, 'debug'):
                    self.log.debug(f"LLM Full Response: {resp_json}")
                
                content = resp_json['choices'][0]['message']['content'].strip()
                self.log.info(f"LLM Raw Output for '{speaker}': '{content}'")
                
                # Clean up extraction - check for dynamic labels
                for s in categories:
                    if s.lower() in content.lower(): 
                        self.log.info(f"Extracted Sentiment: {s}")
                        return s
                
                self.log.warning(f"Could not extract sentiment from LLM response: '{content}'. Defaulting to 'Neutral'.")
                return "Neutral" # Default
            else:
                self.log.error(f"LLM returned non-200 status: {resp.status_code}, Body: {resp.text}")
                return self._fallback_sentiment(text)
        except Exception as e:
             self.log.error(f"LLM Request Exception: {e}")
             return self._fallback_sentiment(text)
    
    def _check_relevance(self, speaker, text):
        """Check if speaker's comments are relevant to the analysis topic"""
        llm_config = self._get_llm_config()
        limit = llm_config.get('max_input_tokens', {}).get('relevance', 12000)

        keywords_list = self.prompts.get('keywords', [])
        keywords_str = ", ".join(map(str, keywords_list)) if isinstance(keywords_list, list) else str(keywords_list)
        topic = self._get_topic()
        
        system_prompt = f"""You are filtering public comments for relevance.

Analysis Instructions / Topic:
{topic}

Keywords: {keywords_str}

Determine if the speaker's statement is relevant to this topic. A statement is relevant if it discusses the topic or any of the keywords.

A statement is NOT relevant if it only discusses:
- Unrelated local issues (dances, community events, housing initiatives unrelated to the topic)
- Procedural matters with no connection to the topic
- Completely different subjects

IMPORTANT: Ignore personal introductions, pleasantries, or rambling starts. Focus on the core message.
Respond with ONLY: Relevant or Not-Relevant"""

        # Increase context to 2500 chars to catch speakers with long intros
        payload_text = text[:limit]
        self.log.info(f"Relevance Check: Sending {len(payload_text)} chars to LLM for speaker '{speaker}' (Limit: {limit})")
        
        user_prompt = f"Speaker: {speaker}\n\nStatement: {payload_text}\n\nRelevance:"
        
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 10
        }
        
        try:
            url = f"{self.api_url.rstrip('/')}/v1/chat/completions"
            resp = requests.post(url, json=payload, timeout=120)
            
            if resp.status_code == 200:
                resp_json = resp.json()
                content = resp_json['choices'][0]['message']['content'].strip()
                self.log.info(f"Relevance check for '{speaker}': '{content}'")
                
                # Check for relevant explicitly
                lower_content = content.lower()
                if 'not-relevant' in lower_content or 'not relevant' in lower_content:
                    self.log.info(f"Skipping irrelevant speaker: {speaker}")
                    return False
                elif 'relevant' in lower_content:
                    return True
                else:
                    return True # Default to true if confusing response
            else:
                # If LLM fails, assume relevant to avoid losing data
                return True
        except Exception as e:
            self.log.error(f"Relevance check exception: {e}")
            return True  # Assume relevant on error

    def _fallback_sentiment(self, text):
        # Fallback: Simple keyword matching when LLM is offline
        keywords_list = self.prompts.get('keywords', [])
        found_keywords = []
        
        text_lower = text.lower()
        for kw in keywords_list:
            if kw.lower() in text_lower:
                found_keywords.append(kw)
        
        if found_keywords:
            # If keywords are found, we mark as 'Neutral' or 'Unknown' but explicitly mention keywords were found
            # The report column is 'Sentiment', so we can't put the whole list there.
            # But the user wants "data in them related to the prompt".
            # If we return "Unknown", the report is empty of meaning.
            # Let's return "Keyword Match" to indicate relevance.
            return "Neutral (Keyword Match)"
        
        return "Unknown (Offline)"

    def _generate_summary(self, speaker, text, mask=False, real_name=None):
        # Generate a concise 3-line summary of the speaker's statement
        llm_config = self._get_llm_config()
        limit = llm_config.get('max_input_tokens', {}).get('summary', 12000)

        # SCRUB REAL NAMES FROM INPUT TEXT TO PREVENT LEAKS
        if mask and real_name and real_name != speaker:
            # Case-insensitive replacement of real name with placeholder or masked ID
            pattern = re.compile(re.escape(real_name), re.IGNORECASE)
            text = pattern.sub("the speaker", text)
            
            # Also try components of name if it's multiple words (e.g., "John Smith")
            parts = real_name.split()
            if len(parts) > 1:
                for part in parts:
                    if len(part) > 2: # Avoid scrubbing common small words
                        pattern = re.compile(r'\b' + re.escape(part) + r'\b', re.IGNORECASE)
                        text = pattern.sub("the speaker", text)

        keywords_list = self.prompts.get('keywords', [])
        keywords_str = ", ".join(map(str, keywords_list)) if isinstance(keywords_list, list) else str(keywords_list)
        
        topic = self._get_topic()
        
        mask_instruction = ""
        if mask:
            mask_instruction = "\n\nCRITICAL: If the provided statement contains the speaker's real name, YOU MUST NOT use it in the summary. Use only the identifier 'the speaker' or the provided masked ID (e.g., Speaker #1234). Do not reveal the person's identity under any circumstances."

        system_prompt = f"""You are summarizing public comments.

Analysis Instructions / Topic:
{topic}

Keywords for context: {keywords_str}

Generate a concise summary of 3-4 sentences covering the speaker's main points and position regarding the topic. Be objective and factual.{mask_instruction}"""

        payload_text = text[:limit]
        self.log.info(f"Summary Generation: Sending {len(payload_text)} chars to LLM for speaker '{speaker}' (Limit: {limit})")

        user_prompt = f"Speaker: {speaker}\n\nStatement: {payload_text}\n\nSummary:"

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,  # Slightly higher for better prose
            "max_tokens": 250  # Increased for 3-4 sentences
        }
        
        try:
            url = f"{self.api_url.rstrip('/')}/v1/chat/completions"
            resp = requests.post(url, json=payload, timeout=120)
            
            if resp.status_code == 200:
                resp_json = resp.json()
                content = resp_json['choices'][0]['message']['content'].strip()
                
                # Strip conversational prefixes using regex for robustness
                content = re.sub(
                    r'(?i)^(?:here is a |this is a )?(?:concise )?(?:summary )?(?:of 3-4 sentences )?(?:covering the speaker\'s main points and positions?|covering the main points and positions?|of what the speaker said)?[.:]?\s*',
                    '',
                    content
                ).strip()
                
                # Double check for the exact phrase just in case
                exact_phrase = "Here is a concise summary of 3-4 sentences covering the speaker's main points and position."
                if content.lower().startswith(exact_phrase.lower()):
                    content = content[len(exact_phrase):].strip()
                
                self.log.info(f"Generated summary for '{speaker}': {content[:50]}...")
                return content
            else:
                self.log.error(f"Summary LLM returned status {resp.status_code}")
                return text[:200] + "..."  # Fallback to truncated text
        except Exception as e:
            self.log.error(f"Summary LLM Exception: {e}")
            return text[:200] + "..."  # Fallback to truncated text

    def _is_none_affiliation(self, a):
        if not a: return True
        a_lower = a.lower().strip()
        
        # Exact matches or starts with
        if a_lower == 'none' or a_lower.startswith('none ('): return True
        if a_lower == 'no affiliation stated': return True
        
        # Keyword matches
        keywords = [
            'no affiliation',
            'no organization',
            'no formal organization',
            'no specific organization',
            '(individual)',
            '(private citizen)',
            '(individual citizen)',
            '(self-identified)'
        ]
        if any(kw in a_lower for kw in keywords): return True
        
        # Specific edge cases from LLM output
        if "speaker's name is mentioned, but no organizational affiliation is provided" in a_lower: return True
        if "speaker's personal affiliation not mentioned" in a_lower: return True
        if "affiliation is not explicitly mentioned" in a_lower: return True
        
        # Individual professions without organization
        if a_lower == 'author': return True
        if a_lower == 'austin small business owner': return True
        if a_lower == 'healthcare worker (specifically in mental health)': return True
        if a_lower == 'licensed professional counselor, palestinian american muslim woman': return True
        if a_lower == 'palestinian christian born and raised in bethlehem': return True
        if a_lower.startswith('resident of district'): return True
        if a_lower == 'district 3 (presumably a local government district)': return True
        if a_lower == 'israeli (note: the speaker mentions being "israeli" but does not provide a specific organization affiliation)': return True
        if a_lower == 'jewish community': return True
        
        return False

    def _format_timestamp(self, seconds):
        """Convert seconds to HH:MM:SS format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"

    def _categorize_affiliations(self, unique_affiliations):
        """Use LLM to categorize a list of unique affiliations into predefined buckets."""
        if not unique_affiliations:
            return {}
            
        # Filter out 'NONE' or similar obvious individuals
        real_orgs = [a for a in unique_affiliations if not self._is_none_affiliation(a)]
        if not real_orgs:
            return {a: "Unaffiliated / Private Citizens" for a in unique_affiliations}

        system_prompt = f"""Categorize the following organizations/affiliations into these EXACT categories:
{chr(10).join(self.org_categories)}

Return a JSON object where the keys are the organization names and the values are the categories.
If an organization doesn't fit well, use the closest fit or 'Unaffiliated / Private Citizens'."""

        user_prompt = f"Organizations to categorize:\n{chr(10).join(real_orgs)}"
        
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "response_format": { "type": "json_object" }
        }
        
        mapping = {}
        try:
            self._spinner_update("Categorizing organizations for executive briefing...")
            url = f"{self.api_url.rstrip('/')}/v1/chat/completions"
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content'].strip()
                mapping = json.loads(content)
        except Exception as e:
            self.log.error(f"Affiliation categorization failed: {e}")
            
        # Fill in defaults if LLM missed any or for individuals
        final_mapping = {}
        for a in unique_affiliations:
            if a in mapping:
                final_mapping[a] = mapping[a]
            elif self._is_none_affiliation(a):
                final_mapping[a] = "Unaffiliated / Private Citizens"
            else:
                final_mapping[a] = "Other / Uncategorized"
        
        return final_mapping

    def _select_representative_voices(self, results, sentiment_categories, count_per_cat=3):
        """Select the best examples of statements for each sentiment category."""
        representative = {cat: [] for cat in sentiment_categories}
        
        for cat in sentiment_categories:
            cat_results = [r for r in results if r['sentiment'] == cat and not r.get('metadata_only')]
            # Sort by summary length and clarity (heuristic: longer summaries often more descriptive)
            cat_results.sort(key=lambda x: len(x['example']), reverse=True)
            
            # Pick top N
            representative[cat] = cat_results[:count_per_cat]
            
        return representative
    def generate_report(self, all_results, report_dir, grand_total_speakers=0, all_meeting_dates=None, all_meetings_metadata=None, mask=False, source_name="City Council", source_slug="CityCouncil", is_individual=False):
        
        # Use the source_name in the title
        title_prefix = f"Speaker Analysis Report - {source_name}"
        briefing_title = f"Executive Briefing: {source_name} {all_results[0].get('meeting', '').split('(')[0].strip() if all_results else ''}"
        
        # Sort results by date (chronologically - earliest first)
        from datetime import datetime
        def parse_date(date_str):
            try:
                # Normalize non-standard months
                clean_date = date_str.replace('Sept ', 'Sep ').replace('Sept. ', 'Sep. ')
                
                # Try parsing common formats
                for fmt in ['%b %d, %Y', '%B %d, %Y', '%Y-%m-%d', '%b. %d, %Y']:
                    try:
                        return datetime.strptime(clean_date, fmt)
                    except:
                        continue
                self.log.warning(f"Failed to parse date: {date_str} (cleaned: {clean_date})")
                return datetime.min  # Fallback for unparseable dates
            except:
                return datetime.min
        
        all_results.sort(key=lambda r: parse_date(r['date']))
        
        # Filter out metadata_only results for statistics and tables
        filtered_results = [r for r in all_results if r.get('metadata_only') is not True]
        
        sentiments = [r['sentiment'] for r in filtered_results]
        total_on_topic = len(sentiments)
        
        # Use the grand total passed in, or default to on-topic count if 0
        total_all_topics = grand_total_speakers if grand_total_speakers > 0 else total_on_topic
        pct_on_topic_val = (total_on_topic / total_all_topics * 100) if total_all_topics > 0 else 0
        
        # Calculate sentiment counts and percentages
        categories = self.prompts.get('sentiment_categories', ['Neutral'])
        all_sentiment_keys = categories + sorted(list(set(sentiments) - set(categories)))
        counts = {s: sentiments.count(s) for s in all_sentiment_keys}
        
        stats = []
        for s in all_sentiment_keys:
            count = counts.get(s, 0)
            pct_on_topic = (count / total_on_topic) * 100 if total_on_topic > 0 else 0
            pct_all = (count / total_all_topics) * 100 if total_all_topics > 0 else 0
            stats.append({
                "sentiment": s,
                "count": count,
                "pct_on_topic": f"{pct_on_topic:.0f}%",
                "pct_all": f"{pct_all:.0f}%"
            })
            
        # Header Info
        topic = self._get_topic()
        
        if all_meeting_dates:
            dates = [d for d in all_meeting_dates if d != 'Unknown Date']
        else:
            dates = [r['date'] for r in filtered_results if r['date'] != 'Unknown Date']
            
        dates_sorted = sorted(dates, key=parse_date)
        
        start_date_str = "Unknown"
        end_date_str = "Unknown"
        
        if dates_sorted:
             d_start = parse_date(dates_sorted[0])
             d_end = parse_date(dates_sorted[-1])
             start_date_str = d_start.strftime('%Y-%m-%d') if d_start != datetime.min else "Unknown"
             end_date_str = d_end.strftime('%Y-%m-%d') if d_end != datetime.min else "Unknown"
             date_range = f"From {dates_sorted[0]} to {dates_sorted[-1]}"
        else:
             date_range = "Unknown"

        mask_suffix = "-masked" if mask else ""
        
        if is_individual:
            filename_detailed = f"Single_Meeting_Report-{source_slug}.md"
            filename_briefing = None # No briefing for individuals
        else:
            filename_detailed = f"Detailed_Speaker_Report-{source_slug}{mask_suffix}_{start_date_str}_to_{end_date_str}.md"
            filename_briefing = f"Executive_Briefing-{source_slug}{mask_suffix}_{start_date_str}_to_{end_date_str}.md"
        
        out_file_detailed_md = os.path.join(report_dir, filename_detailed)
        out_file_briefing_md = os.path.join(report_dir, filename_briefing) if filename_briefing else None
        
        # --- Generate Briefing Data ---

        unique_affiliations = list(set([r.get('affiliation', 'NONE') for r in filtered_results]))
        affiliation_categories = self._categorize_affiliations(unique_affiliations)
        
        sentiment_cats = self.prompts.get('sentiment_categories', ['Neutral'])
        representative_voices = self._select_representative_voices(filtered_results, sentiment_cats)
        
        # --- MARKDOWN DETAILED REPORT ---
        with open(out_file_detailed_md, 'w') as f:
            f.write(f"# Speaker Detailed Report - {source_name}\n\n")
            f.write(f"**Topic**: {topic}\n\n")
            f.write(f"**Prompt**: {self.prompts.get('analysis_instructions', 'Default prompt')}\n\n")
            f.write(f"**Time Period**: {date_range}\n\n")
            f.write(f"**Report Generated**: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n")
            
            if mask or self.fm.get_ai_setting('analysis', 'mask_names'):
                f.write("Names have been anonymized for privacy.\n\n")

            # --- Export Sentiment Manifest for RAG DB Injection (one file per video) ---
            from collections import defaultdict
            per_video = defaultdict(dict)
            for res in all_results: # Use all_results here, including metadata_only
                vid = res.get('summary_file', '').replace('_transcript.json', '')
                if vid:
                    per_video[vid][res['internal_id']] = {
                        "name": res['speaker'],
                        "real_name": res.get('real_name', res['speaker']),
                        "sentiment": res['sentiment']
                    }
            summaries_dir = self.fm.resolve_path('summaries')
            os.makedirs(summaries_dir, exist_ok=True)
            for vid, data_map in per_video.items():
                manifest_path = os.path.join(summaries_dir, f"{vid}_speakers.json")
                with open(manifest_path, 'w', encoding='utf-8') as mf:
                    json.dump(data_map, mf, indent=4)
            
            f.write("## Table of Contents\n")
            f.write("- [Summary Statistics](#summary-statistics)\n")
            f.write("- [Number of Times an On Topic Speaker Spoke at Meetings](#number-of-times-an-on-topic-speaker-spoke-at-meetings)\n")
            f.write("- [Organizations and Affiliations That Spoke](#organizations-and-affiliations-that-spoke---excluding-people-who-represented-only-themselves)\n")
            f.write("- [Meetings Covered in this Report](#meetings-covered-in-this-report)\n")
            f.write("- [Detailed Analysis](#detailed-analysis)\n")
            f.write("\n")
            f.write("## Summary Statistics\n")
            pct_on_topic = (total_on_topic / total_all_topics) * 100 if total_all_topics > 0 else 0
            f.write(f"**Total Speakers (All topics)**: {total_all_topics}\n\n")
            f.write(f"**Count of Speakers on Topic**: {total_on_topic}\n\n")
            f.write(f"**All On Topic Speakers vs All Speakers**: {pct_on_topic:.0f}%\n\n")
            f.write("| Sentiment | Count | Percentage of Total Speakers on Topic | Percentage of Total Speakers |\n")
            f.write("|---|---|---|---|\n")
            for stat in stats:
                f.write(f"| {stat['sentiment']} | {stat['count']} | {stat['pct_on_topic']} | {stat['pct_all']} |\n")
            f.write("\n")
            
            # --- New Table 1: Speaker Frequency ---
            f.write("## Number of Times an On Topic Speaker Spoke at Meetings\n")
            f.write("| Name | Number of Times Speaking | Sentiment | Meetings Spoken At |\n")
            f.write("|---|---|---|---|\n")
            
            # Aggregate by speaker name
            speaker_counts = {}
            for res in filtered_results: # Use filtered_results here
                if res.get('metadata_only'): continue
                name = res['speaker']
                if name not in speaker_counts:
                    speaker_counts[name] = {'count': 0, 'sentiments': [], 'meetings': set()}
                speaker_counts[name]['count'] += 1
                speaker_counts[name]['sentiments'].append(res['sentiment'])
                speaker_counts[name]['meetings'].add(res['meeting'])
            
            # Sort by count desc
            sorted_speakers = sorted(speaker_counts.items(), key=lambda x: x[1]['count'], reverse=True)
            
            for name, data in sorted_speakers:
                # Most common sentiment
                from collections import Counter
                common_s = Counter(data['sentiments']).most_common(1)[0][0]
                # Format meetings list
                meetings_str = "<br>".join(sorted(data['meetings']))
                f.write(f"| {name} | {data['count']} | {common_s} | {meetings_str} |\n")
            f.write("\n")

            # --- New Table 2: Organization Frequency ---
            f.write("## Organizations and Affiliations That Spoke - Excluding People Who Represented Only Themselves\n")
            f.write("| Organization name | Number of Speakers | Sentiment | Meetings Spoken At |\n")
            f.write("|---|---|---|---|\n")

            # Aggregate by Organization
            org_counts = {}
            
            for res in filtered_results: # Use filtered_results here
                if res.get('metadata_only'): continue
                affil = res.get('affiliation', '').strip()
                
                if self._is_none_affiliation(affil):
                    affil = 'None (Individuals)'
                
                if affil not in org_counts:
                    # using set to count unique speakers
                    org_counts[affil] = {'speakers': set(), 'sentiments': [], 'meetings': set()}
                
                org_counts[affil]['speakers'].add(res['speaker'])
                org_counts[affil]['sentiments'].append(res['sentiment'])
                org_counts[affil]['meetings'].add(res['meeting'])
            
            # Sort by unique speaker count desc
            sorted_orgs = sorted(org_counts.items(), key=lambda x: len(x[1]['speakers']), reverse=True)
            
            for org, data in sorted_orgs:
                count = len(data['speakers'])
                # Most common sentiment
                from collections import Counter
                common_s = Counter(data['sentiments']).most_common(1)[0][0]
                meetings_str = "<br>".join(sorted(data['meetings']))
                f.write(f"| {org} | {count} | {common_s} | {meetings_str} |\n")
            f.write("\n")
            
            # --- New Table 3: Meetings Covered in This Report ---
            if all_meetings_metadata:
                f.write("## Meetings Covered in This Report\n")
                f.write("| Meeting | Date | On Topic Speakers? |\n")
                f.write("|---|---|---|\n")
                
                # Sort by date
                sorted_meetings = sorted(all_meetings_metadata, key=lambda x: parse_date(x['date']))
                
                for m in sorted_meetings:
                    on_topic = "Yes" if m['has_on_topic'] else "No"
                    f.write(f"| {m['meeting']} | {m['date']} | {on_topic} |\n")
                f.write("\n")

            f.write("## Detailed Analysis\n")
            f.write("| Speaker | Affiliation | Sentiment | Summarized Statements | Meeting | Summary File | Original Video |\n")
            f.write("|---|---|---|---|---|---|---|\n")
            for res in filtered_results:
                if res.get('metadata_only') is True: continue
                clean_ex = res['example'].replace('\n', ' ')[:500]  # Expanded for longer summaries
                affil = res.get('affiliation', '')
                if not affil or affil.strip() == '' or affil.upper() == 'NONE': affil = "NONE"
                # Format timestamp for link text
                timestamp_link = self._format_timestamp(res['start_time'])
                # Use pre-formatted video link
                video_url_with_timestamp = res['original_video']
                f.write(f"| {res['speaker']} | {affil} | {res['sentiment']} | {clean_ex} | {res['meeting']} | [{res['summary_file']}](../../transcripts/{res['summary_file']}) | [{timestamp_link}]({video_url_with_timestamp}) |\n")
            
            f.write("\n---\n")
            f.write("© Copyright 2026. Joel Greenberg. All Rights Reserved. Contact the author at joelontheroad@proton.me\n")

        self.log.success(f"Markdown Detailed Report generated: {out_file_detailed_md}")

        # --- HTML DETAILED REPORT ---
        html_detailed = out_file_detailed_md.replace('.md', '.html')
        with open(html_detailed, 'w') as f:
            # High-End Shared CSS
            style = """
            :root {
                --primary: #0f172a;
                --secondary: #334155;
                --accent-blue: #2563eb;
                --accent-red: #dc2626;
                --bg: #f8fafc;
                --card-bg: #ffffff;
                --text-main: #1e293b;
                --text-muted: #64748b;
                --border: #e2e8f0;
            }
            body { 
                font-family: 'Inter', -apple-system, sans-serif; 
                background: var(--bg); 
                color: var(--text-main);
                margin: 0; padding: 0; 
                line-height: 1.6;
            }
            .header {
                background: var(--primary);
                color: white;
                padding: 3rem 2rem;
                text-align: center;
                box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
            }
            .header h1 { margin: 0; font-size: 2.5rem; letter-spacing: -0.025em; }
            .header p { font-size: 1.25rem; opacity: 0.8; margin-top: 0.5rem; }
            .header .meta { 
                margin-top: 1rem; 
                font-family: monospace; 
                color: #94a3b8; 
                text-transform: uppercase; 
                letter-spacing: 0.1em; 
            }
            .container { max-width: 1200px; margin: -2rem auto 4rem; padding: 0 1rem; }
            .dashboard {
                display: flex;
                flex-wrap: nowrap;
                overflow-x: auto;
                gap: 1rem;
                margin-bottom: 2rem;
                padding-bottom: 1rem;
            }
            .stat-card {
                flex: 1;
                min-width: 140px;
                background: var(--card-bg);
                padding: 1.25rem;
                border-radius: 0.75rem;
                box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1);
                text-align: center;
                border: 1px solid var(--border);
            }
            .stat-card .label { color: var(--text-muted); font-size: 0.75rem; font-weight: 600; text-transform: uppercase; margin-bottom: 0.5rem; text-align: center; }
            .stat-card .value { font-size: 2rem; font-weight: 800; color: var(--primary); text-align: center; }
            
            .content-section {
                background: var(--card-bg);
                padding: 2.5rem;
                border-radius: 1rem;
                box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
                margin-bottom: 2rem;
                border: 1px solid var(--border);
                overflow-x: auto;
            }
            
            table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }
            th { text-align: left; color: var(--text-muted); text-transform: uppercase; font-size: 0.75rem; padding: 1rem; border-bottom: 2px solid var(--border); }
            td { padding: 1rem; border-bottom: 1px solid var(--border); }
            
            .pill {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 0.25rem 0.75rem;
                border-radius: 9999px;
                font-size: 0.7rem;
                font-weight: 700;
                text-transform: uppercase;
                text-align: center;
                min-width: 100px;
            }
            /* PILL_STYLES_PLACEHOLDER */
            
            .watch-btn {
                background: var(--primary);
                color: white;
                text-decoration: none;
                padding: 0.4rem 0.8rem;
                border-radius: 0.375rem;
                font-size: 0.75rem;
                font-weight: 600;
                transition: background 0.2s;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                text-align: center;
                min-width: 120px;
            }
            .watch-btn:hover { background: var(--accent-blue); }
            .center-col { text-align: center; }
            """
            
            sentiment_colors = [
                {"bg": "#dbeafe", "fg": "#1e40af"}, # blue
                {"bg": "#fee2e2", "fg": "#991b1b"}, # red
                {"bg": "#dcfce7", "fg": "#166534"}, # green
                {"bg": "#f3e8ff", "fg": "#6b21a8"}, # purple
                {"bg": "#fef3c7", "fg": "#92400e"}  # yellow
            ]
            pill_styles = ""
            for i, cat in enumerate(self.prompts.get('sentiment_categories', ['Neutral'])):
                color = sentiment_colors[i % len(sentiment_colors)]
                slug = cat.lower().replace(' ', '-')
                pill_styles += f".pill-{slug} {{ background: {color['bg']}; color: {color['fg']}; }}\n            "
            if ".pill-neutral" not in pill_styles:
                pill_styles += ".pill-neutral { background: #f1f5f9; color: #475569; }\n            "
                
            style = style.replace("/* PILL_STYLES_PLACEHOLDER */", pill_styles)
            
            title_text = f"{title_prefix} - {date_range}"
            f.write(f"<!DOCTYPE html><html><head><title>{title_text}</title><style>{style}</style></head><body>")
            
            # Header
            f.write(f"<div class='header'>")
            f.write(f"<div class='meta'>|| COMPREHENSIVE ANALYSIS ||</div>")
            f.write(f"<h1>{source_name}: Speaker Detailed Report</h1>")
            f.write(f"<p>{date_range}</p>")
            f.write(f"<p style='font-size: 0.9rem; margin-top: 1rem;'>Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>")
            f.write(f"</div>")
            
            f.write("<div class='container'>")
            
            # Dashboard
            f.write("<div class='dashboard'>")
            f.write(f"<div class='stat-card'><div class='label'>Total Speakers</div><div class='value'>{total_all_topics}</div></div>")
            f.write(f"<div class='stat-card'><div class='label'>On-topic speakers</div><div class='value'>{total_on_topic}</div></div>")
            for stat in stats:
                f.write(f"<div class='stat-card'><div class='label'>{stat['sentiment']}</div><div class='value'>{stat['pct_on_topic']}</div></div>")
            f.write("</div>")
            
            pct_on_topic_val = (total_on_topic / total_all_topics * 100) if total_all_topics > 0 else 0
            f.write(f"<div style='text-align: center; margin-bottom: 2rem; font-weight: 700; font-size: 1.2rem; color: var(--primary);'>Percentage of Speakers on Topic: {pct_on_topic_val:.1f}%</div>")

            # Check if this report likely uses Box media (by inspecting the first non-metadata result)
            uses_box = any('box.com' in r.get('original_video', '') for r in filtered_results)
            if uses_box:
                f.write("<div style='text-align: center; margin-bottom: 2rem; font-size: 0.9rem; color: var(--accent-red); padding: 0 2rem;'><em>Note: Linking into media files is not natively supported by Box.com. Audio files will resume from your last paused position or the beginning of the meeting. Please use the timecodes under 'Watch Video' to navigate manually.</em></div>")

            # Methodology Component
            f.write("<div class='content-section'>")
            f.write("<h2>Full Analysis Context</h2>")
            f.write(f"<p><strong>Topic:</strong> {topic}</p>")
            f.write(f"<p style='font-family: monospace; font-size: 0.8rem; background: #f1f5f9; padding: 1rem; border-radius: 0.5rem;'><strong>Prompt:</strong> {self.prompts.get('analysis_instructions', 'Default prompt')}</p>")
            if mask or self.fm.get_ai_setting('analysis', 'mask_names'):
                f.write(f"<p style='color: white; font-weight: bold;'>PRIVACY NOTICE: Names have been anonymized for privacy.</p>")
            f.write("</div>")
                
            # HTML Table 1
            f.write("<div class='content-section'>")
            f.write("<h2>Speaker Frequency Analysis</h2>")
            f.write("<table><thead><tr><th>Name</th><th>Meetings</th><th>Primary Sentiment</th></tr></thead><tbody>")
            for name, data in sorted_speakers:
                from collections import Counter
                common_s = Counter(data['sentiments']).most_common(1)[0][0]
                cat_pill = f"pill pill-{common_s.lower().replace(' ', '-')}"
                f.write(f"<tr><td><strong>{name}</strong></td><td>{data['count']}</td><td><span class='{cat_pill}'>{common_s}</span></td></tr>")
            f.write("</tbody></table>")
            f.write("</div>")

            # HTML Table 2
            f.write("<div class='content-section'>")
            f.write("<h2>Organizational Presence</h2>")
            f.write("<table><thead><tr><th>Organization</th><th>Unique Speakers</th><th>Primary Sentiment</th></tr></thead><tbody>")
            for org, data in sorted_orgs:
                count = len(data['speakers'])
                from collections import Counter
                common_s = Counter(data['sentiments']).most_common(1)[0][0]
                cat_pill = f"pill pill-{common_s.lower().replace(' ', '-')}"
                f.write(f"<tr><td>{org}</td><td>{count}</td><td><span class='{cat_pill}'>{common_s}</span></td></tr>")
            f.write("</tbody></table>")
            f.write("</div>")
            
            # HTML Table 3: Meetings Covered
            if all_meetings_metadata:
                f.write("<div class='content-section'>")
                f.write("<h2>Meetings Analyzed</h2>")
                f.write("<table><thead><tr><th>Meeting Title</th><th>Date</th><th>Relevant Comments</th></tr></thead><tbody>")
                sorted_meetings = sorted(all_meetings_metadata, key=lambda x: parse_date(x['date']))
                for m in sorted_meetings:
                    on_topic = "Yes" if m['has_on_topic'] else "No"
                    f.write(f"<tr><td>{m['meeting']}</td><td>{m['date']}</td><td>{on_topic}</td></tr>")
                f.write("</tbody></table>")
                f.write("</div>")

            # Detailed Analysis
            f.write("<div class='content-section'>")
            f.write("<h2>Detailed Speaker Analysis</h2>")
            f.write("""
                <table>
                    <thead>
                    <tr>
                        <th>Speaker</th>
                        <th class='center-col'>Affiliation</th>
                        <th class='center-col'>Sentiment</th>
                        <th>Summarized Statement</th>
                        <th class='center-col'>Watch Video</th>
                        <th class='center-col'>Meeting</th>
                    </tr>
                </thead>
                <tbody>
            """)
            
            for res in filtered_results:
                clean_ex = res['example'].replace('\n', ' ')
                affil = res.get('affiliation', '')
                if not affil or affil.strip() == '' or affil.upper() == 'NONE': affil = "NONE"
                video_url_with_timestamp = res['original_video']
                timestamp_link = self._format_timestamp(res['start_time'])
                cat_pill = f"pill pill-{res['sentiment'].lower().replace(' ', '-')}"
                
                f.write("<tr>")
                f.write(f"<td><strong>{res['speaker']}</strong><br><small style='color: var(--text-muted)'>{res['meeting']}</small></td>")
                f.write(f"<td class='center-col'>{affil}</td>")
                f.write(f"<td class='center-col'><span class='{cat_pill}'>{res['sentiment']}</span></td>")
                f.write(f"<td style='min-width: 300px;'>{clean_ex}</td>")
                f.write(f"<td class='center-col'><a href='{video_url_with_timestamp}' target='_blank' class='watch-btn'>Watch at {timestamp_link}</a></td>")
                f.write(f"<td class='center-col'>{res.get('date', '')}</td>")
                f.write("</tr>")
            f.write("</tbody></table>")
            f.write("</div>")
            
            f.write("<div style='text-align: center; color: var(--text-muted); font-size: 0.8rem; padding: 2rem;'>")
            f.write("&copy; Copyright 2026. Joel Greenberg. All Rights Reserved. Contact the author at joelontheroad@proton.me")
            f.write("</div>")
            f.write("</div></body></html>")

        self.log.success(f"HTML Detailed Report generated: {html_detailed}")

        # --- HTML EXECUTIVE BRIEFING ---
        if out_file_briefing_md:
            # --- Markdown Executive Briefing ---
            with open(out_file_briefing_md, 'w') as f:
                f.write(f"# {briefing_title}\n\n")
                f.write(f"**Topic**: {topic}\n")
                f.write(f"**Time Period**: {date_range}\n\n")
                f.write(f"**Report Generated**: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n")
                
                if mask or self.fm.get_ai_setting('analysis', 'mask_names'):
                    f.write("Names have been anonymized for privacy.\n\n")

                f.write("## Dashboard\n")
                f.write(f"- Total Speakers Analyzed: {total_all_topics}\n")
                f.write(f"- Speakers on Topic: {total_on_topic} ({pct_on_topic_val:.1f}%)\n")
                for s in stats:
                    f.write(f"- {s['sentiment']}: {s['count']} ({s['pct_on_topic']} of on-topic)\n")
                f.write("\n")

            # --- HTML EXECUTIVE BRIEFING ---
            html_briefing = out_file_briefing_md.replace('.md', '.html')
            with open(html_briefing, 'w') as f:
                # Modern, High-End CSS
                style = """
                :root {
                    --primary: #0f172a;
                    --secondary: #334155;
                    --accent-blue: #2563eb;
                    --accent-red: #dc2626;
                    --bg: #f8fafc;
                    --card-bg: #ffffff;
                    --text-main: #1e293b;
                    --text-muted: #64748b;
                    --border: #e2e8f0;
                }
                body { 
                    font-family: 'Inter', -apple-system, sans-serif; 
                    background: var(--bg); 
                    color: var(--text-main);
                    margin: 0; padding: 0; 
                    line-height: 1.6;
                }
                .header {
                    background: var(--primary);
                    color: white;
                    padding: 3rem 2rem;
                    text-align: center;
                    box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
                }
                .header h1 { margin: 0; font-size: 2.5rem; letter-spacing: -0.025em; }
                .header .meta { 
                    margin-top: 1rem; 
                    font-family: monospace; 
                    color: #94a3b8; 
                    text-transform: uppercase; 
                    letter-spacing: 0.1em; 
                }
                .container { max-width: 1000px; margin: -2rem auto 4rem; padding: 0 1rem; }
                .dashboard {
                    display: flex;
                    flex-wrap: nowrap;
                    overflow-x: auto;
                    gap: 1rem;
                    margin-bottom: 2rem;
                    padding-bottom: 1rem;
                }
                .stat-card {
                    flex: 1;
                    min-width: 140px;
                    background: var(--card-bg);
                    padding: 1.25rem;
                    border-radius: 0.75rem;
                    box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1);
                    text-align: center;
                    border: 1px solid var(--border);
                }
                .stat-card .label { color: var(--text-muted); font-size: 0.75rem; font-weight: 600; text-transform: uppercase; margin-bottom: 0.5rem; }
                .stat-card .value { font-size: 2rem; font-weight: 800; color: var(--primary); }
                
                .content-section {
                    background: var(--card-bg);
                    padding: 2.5rem;
                    border-radius: 1rem;
                    box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
                    margin-bottom: 2rem;
                    border: 1px solid var(--border);
                }
                .executive-summary {
                    border-left: 5px solid var(--accent-blue);
                    background: #f1f5f9;
                    padding: 1.5rem;
                    font-style: italic;
                    font-size: 1.1rem;
                    margin: 1.5rem 0;
                }
                .methodology {
                    background: #1e293b;
                    color: #cbd5e1;
                    padding: 1.5rem;
                    border-radius: 0.5rem;
                    font-family: 'Fira Code', monospace;
                    font-size: 0.85rem;
                    margin-bottom: 2rem;
                }
                .methodology h3 { color: white; margin-top: 0; font-size: 1rem; }
                
                table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
                th { text-align: left; color: var(--text-muted); text-transform: uppercase; font-size: 0.75rem; padding: 1rem; border-bottom: 2px solid var(--border); }
                td { padding: 1rem; border-bottom: 1px solid var(--border); }
                
                .pill {
                    display: inline-block;
                    padding: 0.25rem 0.75rem;
                    border-radius: 9999px;
                    font-size: 0.7rem;
                    font-weight: 700;
                    text-transform: uppercase;
                }
                /* PILL_STYLES_PLACEHOLDER */
                
                .voice-card {
                    border: 1px solid var(--border);
                    border-radius: 0.5rem;
                    padding: 1.5rem;
                    margin-bottom: 1rem;
                }
                .voice-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
                .voice-speaker { font-weight: 700; font-size: 1.1rem; }
                .watch-btn {
                    background: var(--primary);
                    color: white;
                    text-decoration: none;
                    padding: 0.5rem 1rem;
                    border-radius: 0.375rem;
                    font-size: 0.8rem;
                    font-weight: 600;
                    transition: background 0.2s;
                }
                .watch-btn:hover { background: var(--accent-blue); }
                """
                
                sentiment_colors = [
                    {"bg": "#dbeafe", "fg": "#1e40af"}, # blue
                    {"bg": "#fee2e2", "fg": "#991b1b"}, # red
                    {"bg": "#dcfce7", "fg": "#166534"}, # green
                    {"bg": "#f3e8ff", "fg": "#6b21a8"}, # purple
                    {"bg": "#fef3c7", "fg": "#92400e"}  # yellow
                ]
                pill_styles = ""
                for i, cat in enumerate(self.prompts.get('sentiment_categories', ['Neutral'])):
                    color = sentiment_colors[i % len(sentiment_colors)]
                    slug = cat.lower().replace(' ', '-')
                    pill_styles += f".pill-{slug} {{ background: {color['bg']}; color: {color['fg']}; }}\n                "
                if ".pill-neutral" not in pill_styles:
                    pill_styles += ".pill-neutral { background: #f1f5f9; color: #475569; }\n                "
                    
                style = style.replace("/* PILL_STYLES_PLACEHOLDER */", pill_styles)
                
                # Start HTML
                f.write(f"<!DOCTYPE html><html><head><title>{briefing_title}</title><style>{style}</style></head><body>")
                
                # Header
                f.write(f"<div class='header'>")
                f.write(f"<div class='meta'>INTELLIGENCE BRIEF // OFFICIAL RECORD</div>")
                f.write(f"<h1>{source_name}: Speaker Analysis Briefing</h1>")
                f.write(f"<p style='font-size: 1.25rem; opacity: 0.8; margin-top: 0.5rem;'>{date_range}</p>")
                f.write(f"<p style='font-size: 0.9rem; margin-top: 1rem; color: #cbd5e1;'>Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>")
                f.write(f"</div>")
                
                f.write("<div class='container'>")
                
                if mask or self.fm.get_ai_setting('analysis', 'mask_names'):
                    f.write("<div style='text-align: center; margin-bottom: 2rem; color: white; font-weight: bold;'>PRIVACY NOTICE: Names have been anonymized for privacy.</div>")

                # Dashboard
                f.write("<div class='dashboard'>")
                eb_items = []
                eb_items.append(f"<div class='stat-card'><div class='label'>Total Speakers</div><div class='value'>{total_all_topics}</div></div>")
                eb_items.append(f"<div class='stat-card'><div class='label'>On-topic speakers</div><div class='value'>{total_on_topic}</div></div>")
                for stat in stats:
                    eb_items.append(f"<div class='stat-card'><div class='label'>{stat['sentiment']}</div><div class='value'>{stat['pct_on_topic']}</div></div>")
                
                for item in eb_items[::-1]:
                    f.write(item)
                f.write("</div>")
                
                if uses_box:
                    f.write("<div style='text-align: center; margin-bottom: 2rem; font-size: 0.9rem; color: var(--accent-red); padding: 0 2rem;'><em>Note: Linking into media files is not natively supported by Box.com. Audio files will resume from your last paused position or the beginning of the meeting. Please use the timecodes under 'Watch Video' to navigate manually.</em></div>")

                # Methodology
                f.write("<div class='methodology'>")
                f.write("<h3>Dataset Methodology</h3>")
                f.write(f"PROMPT SOURCE: {self.prompts.get('analysis_instructions', 'Default System Prompt')}<br><br>")
                f.write(f"SENTIMENT CLASSES: {', '.join(sentiment_cats)}<br>")
                f.write(f"SCOPE: Generated on {datetime.now().strftime('%Y-%m-%d')} for {source_name} workspace.")
                f.write("</div>")
                
                # Top 10 Speakers
                f.write("<div class='content-section'>")
                f.write("<h2>Most Frequent Speakers</h2>")
                f.write("<table><thead><tr><th>Name</th><th>Appearances</th><th>Primary Sentiment</th></tr></thead><tbody>")
                for name, data in sorted_speakers[:10]:
                     from collections import Counter
                     common_s = Counter(data['sentiments']).most_common(1)[0][0]
                     cat_pill = f"pill pill-{common_s.lower().replace(' ', '-')}"
                     f.write(f"<tr><td><strong>{name}</strong></td><td>{data['count']} meetings</td><td><span class='{cat_pill}'>{common_s}</span></td></tr>")
                f.write("</tbody></table>")
                f.write("</div>")
                
                # Categorized Organizations
                f.write("<div class='content-section'>")
                f.write("<h2>Organizational Footprint</h2>")
                
                # Group orgs by category
                by_category = {cat: [] for cat in self.org_categories}
                for org, data in sorted_orgs:
                    cat = affiliation_categories.get(org, "Other / Uncategorized")
                    if cat in by_category:
                        by_category[cat].append((org, data))
                    else:
                        if "Other / Uncategorized" not in by_category: by_category["Other / Uncategorized"] = []
                        by_category["Other / Uncategorized"].append((org, data))
                
                for cat_name, org_list in by_category.items():
                    if not org_list: continue
                    # filter individual None and empty strings from advocacy lists
                    filtered_org_list = [o for o in org_list if o[0] != 'None (Individuals)']
                    if not filtered_org_list and cat_name != "Unaffiliated / Private Citizens": continue
                    
                    # If we're in Private Citizens, we WANT the None(Individuals)
                    display_list = org_list if cat_name == "Unaffiliated / Private Citizens" else filtered_org_list
                    if not display_list: continue

                    f.write(f"<h3>{cat_name}</h3>")
                    f.write("<table><thead><tr><th>Organization</th><th>Speakers</th><th>Sentiment</th></tr></thead><tbody>")
                    for org, data in display_list:
                        from collections import Counter
                        common_s = Counter(data['sentiments']).most_common(1)[0][0]
                        cat_pill = f"pill pill-{common_s.lower().replace(' ', '-')}"
                        f.write(f"<tr><td>{org}</td><td>{len(data['speakers'])}</td><td><span class='{cat_pill}'>{common_s}</span></td></tr>")
                    f.write("</tbody></table>")
                f.write("</div>")
                
                # Representative Voices
                f.write("<div class='content-section'>")
                f.write("<h2>Representative Voices</h2>")
                f.write("<p style='color: var(--text-muted); margin-bottom: 2rem;'>Key testimony excerpts that encapsulate the core sentiment of each side.</p>")
                
                for cat in sentiment_cats:
                    voices = representative_voices.get(cat, [])
                    if not voices: continue
                    
                    f.write(f"<div style='margin-top: 2rem; border-top: 2px solid var(--border); padding-top: 1rem;'>")
                    f.write(f"<h3 style='margin-bottom: 1.5rem;'>Position Category: {cat}</h3>")
                    for voice in voices:
                        f.write("<div class='voice-card'>")
                        f.write("<div class='voice-header'>")
                        f.write(f"<span class='voice-speaker'>{voice['speaker']}</span>")
                        f.write(f"<a href='{voice['original_video']}' target='_blank' class='watch-btn'>Watch Speaker</a>")
                        f.write("</div>")
                        f.write(f"<p>{voice['example']}</p>")
                        f.write(f"<div style='font-size: 0.75rem; color: var(--text-muted);'>{voice['meeting']}</div>")
                        f.write("</div>")
                    f.write("</div>")
                f.write("</div>")
                
                f.write("<div style='text-align: center; color: var(--text-muted); font-size: 0.8rem; padding: 2rem;'>")
                f.write("REDACTED / FOR INTERNAL REVIEW ONLY // GENERATED BY SPEAKER ANALYZER")
                f.write("</div>")
                f.write("</div></body></html>")
                
            self.log.success(f"Executive Briefing generated: {html_briefing}")
