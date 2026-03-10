#!/usr/bin/env ./.venv/bin/python3
# **********************************************************
# Public Meeting Speaker Analyzer
# file: argument-analyzer.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import sys
if not (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)):
    print("Error: Virtual environment not activated.")
    print("Try running: source .venv/bin/activate") 
    sys.exit(1)
import argparse, os, json
import datetime
import requests
import yaml
import re

from utils.logger import Logger
from utils.file_manager import FileManager
from utils.preflight import Preflight
from utils.discovery import get_available_connectors

start_time = datetime.datetime.now()
print(f"Starting Semantic Argument Analyzer at {start_time.strftime('%I:%M %p %Y-%m-%d')}...")

class ArgumentAnalyzer:
    def __init__(self, logger, file_manager, mask=False):
        self.log = logger
        self.fm = file_manager
        self.mask = mask
        self.log.info(f"Connector Slug: {self.fm.connector_slug}")
        self.log.info(f"Transcripts Path Resolved: {self.fm.resolve_path('transcripts')}")
        # Load prompts directly from config via FileManager (standardized in earlier turns)
        # But for standalone, we reload them
        self.prompts = self.fm.load_yaml("configs/prompts.yaml")
        
        self.api_url = self.fm.get_network_setting('llm_api_url')
        if not self.api_url: self.api_url = "http://127.0.0.1:1234"
        
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0

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
        return self.fm.config.get('ai_settings', {}).get('llm', {})

    def _spinner_update(self, message):
        sys.stdout.write(f"\r[{self._get_spinner()}] {message}")
        sys.stdout.flush()

    def _spinner_done(self):
        print()

    def _check_relevance(self, speaker, text):
        """Check if speaker's comments are relevant to the analysis topic."""
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

        payload_text = text[:limit]
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
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content'].strip()
                if 'relevant' in content.lower() and 'not' not in content.lower():
                    return True
                return False
            return True
        except Exception:
            return True

    def _analyze_sentiment(self, speaker, text):
        """Classify sentiment."""
        llm_config = self._get_llm_config()
        limit = llm_config.get('max_input_tokens', {}).get('sentiment', 12000)
        topic = self._get_topic()
        sentiment_instructions = self.prompts.get('sentiment_instructions', '')
        categories = self.prompts.get('sentiment_categories', ['Neutral'])
        categories_str = ", ".join(categories)
        
        system_prompt = f"""You are analyzing public comment sentiment on the following topic: {topic}.

{sentiment_instructions}

Respond with ONLY these exact labels: {categories_str}."""

        user_prompt = f"Speaker: {speaker}\n\nStatement: {text[:limit]}\n\nSentiment:"
        
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
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content'].strip()
                categories = self.prompts.get('sentiment_categories', ['Neutral'])
                for s in categories:
                    if s.lower() in content.lower(): return s
            return "Neutral"
        except Exception:
            return "Neutral"

    def _extract_raw_arguments(self, speaker, text):
        """Phase 1: Ask the LLM to extract 1-3 distinct arguments from a single speaker's text."""
        llm_config = self._get_llm_config()
        limit = llm_config.get('max_input_tokens', {}).get('summary', 12000)
        
        system_prompt = """You are analyzing public comments.
Extract the 1 to 3 core arguments, claims, or rhetorical points made by this speaker.
Return the arguments as a JSON list of objects, where each object has:
- "argument": A concise summary of the point.
- "quote": A short, verbatim snippet (6-10 words) from the provided text that illustrates this argument. This quote will be used to find the exact timestamp.

DO NOT return markdown. Only return valid JSON."""

        user_prompt = f"Speaker Statement: {text[:limit]}"
        
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 500
        }
        
        try:
            url = f"{self.api_url.rstrip('/')}/v1/chat/completions"
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content'].strip()
                if content.startswith('```json'): content = content[7:]
                if content.startswith('```'): content = content[3:]
                if content.endswith('```'): content = content[:-3]
                try:
                    args = json.loads(content)
                    if isinstance(args, list): return args
                except: pass
            return []
        except: return []

    def _get_embedding(self, text):
        url = f"{self.api_url.rstrip('/')}/v1/embeddings"
        emb_model = self.fm.get_ai_setting('rag', 'embedding_model') or 'nomic-embed-text-v1.5'
        try:
            resp = requests.post(url, json={"input": text, "model": emb_model}, timeout=30)
            if resp.status_code == 200:
                return resp.json()['data'][0]['embedding']
        except: pass
        return None

    def _cluster_by_embeddings(self, raw_arguments, sentiment, threshold=0.90):
        try:
            import numpy as np
        except ImportError:
            return [{'canonical': a, 'raw_matches': [a]} for a in raw_arguments]

        unique_args = list(dict.fromkeys(raw_arguments))
        self._spinner_update(f"Embedding {len(unique_args)} {sentiment} arguments...")

        vectors = []
        valid_args = []
        for arg in unique_args:
            vec = self._get_embedding(arg)
            if vec is not None:
                vectors.append(np.array(vec, dtype=np.float32))
                valid_args.append(arg)

        if not vectors:
            return [{'canonical': a, 'raw_matches': [a]} for a in unique_args]

        norms = np.array([np.linalg.norm(v) for v in vectors])
        norms[norms == 0] = 1
        normed = np.array([v / n for v, n in zip(vectors, norms)])

        assigned = [False] * len(valid_args)
        clusters = []

        for i in range(len(valid_args)):
            if assigned[i]: continue
            sims = normed @ normed[i]
            members = [j for j, s in enumerate(sims) if s >= threshold and not assigned[j]]
            for j in members: assigned[j] = True
            member_texts = [valid_args[j] for j in members]
            canonical = max(member_texts, key=len)
            clusters.append({'canonical': canonical, 'raw_matches': member_texts})

        return clusters

    def run_pipeline(self, source_name="City Council", source_slug="CityCouncil"):
        trans_dir = self.fm.resolve_path('transcripts')
        if not os.path.exists(trans_dir):
            self.log.error("No transcripts folder found.")
            return

        files = [f for f in os.listdir(trans_dir) if f.endswith('_transcript.json')]
        if not files:
            self.log.error(f"No transcripts found in: {trans_dir}")
            self.log.info(f"Directory total file count: {len(os.listdir(trans_dir))}")
            return
            
        categories = self.prompts.get('sentiment_categories', ['Neutral'])
        raw_args_pool = {cat: [] for cat in categories}
        if 'Unknown' not in raw_args_pool: raw_args_pool['Unknown'] = []
        
        arg_to_speakers = {}
        arg_to_links = {}
        all_dates = []
        speaker_sentiments = {}

        total_files = len(files)
        for i, f_name in enumerate(files, 1):
            vid_id = f_name.replace('_transcript.json', '')
            trans_path = os.path.join(trans_dir, f_name)
            
            with open(trans_path, 'r') as f: data = json.load(f)

            summaries_dir = self.fm.resolve_path('summaries')
            meta_path = os.path.join(summaries_dir, f"{vid_id}_metadata.json")
            source_url = ''; offset = 0; speaker_manifest = {}
            if os.path.exists(meta_path):
                with open(meta_path, 'r') as mf:
                    meta = json.load(mf)
                    source_url = meta.get('source_url', '')
                    offset = int(meta.get('offset', 0))
                    if meta.get('date'): all_dates.append(meta['date'])

            manifest_path = os.path.join(summaries_dir, f"{vid_id}_speakers.json")
            if os.path.exists(manifest_path):
                with open(manifest_path, 'r') as mf: speaker_manifest = json.load(mf)

            speaker_starts = {}; speaker_text = {}
            for seg in data.get('segments', []):
                speaker = seg.get('speaker', 'Unknown')
                if speaker not in speaker_text:
                    speaker_text[speaker] = []
                    speaker_starts[speaker] = int(seg.get('start', 0))
                speaker_text[speaker].append(seg.get('text', '').strip())
                
            total_speakers = len(speaker_text)
            current = 0
            for orig_spk, texts in speaker_text.items():
                full_text = " ".join(texts)
                if len(full_text) < 50: continue
                current += 1
                
                self._spinner_update(f"[{i}/{total_files}] Extracting arguments from {vid_id} (Speaker {current}/{total_speakers})")
                
                resolved_info = speaker_manifest.get(orig_spk, {})
                resolved_name = resolved_info.get('name', orig_spk)
                real_name = resolved_info.get('real_name', resolved_name)
                
                if self.mask and real_name != 'Unknown':
                    spk = f"Speaker #{abs(hash(real_name)) % 10000:04d}"
                else: 
                    # If not masking, use real name if available
                    spk = real_name
                
                if not self._check_relevance(spk, full_text): continue
                sentiment = self._analyze_sentiment(spk, full_text)
                speaker_sentiments[f"{vid_id}_{orig_spk}"] = sentiment

                spk_segments = []
                for seg in data.get('segments', []):
                    if seg.get('speaker', 'Unknown') == orig_spk:
                        spk_segments.append({'start': int(seg.get('start', 0)), 'text': seg.get('text', '').strip().lower()})

                extracted_data = self._extract_raw_arguments(spk, full_text)

                for entry in extracted_data:
                    if not isinstance(entry, dict): continue
                    arg = entry.get('argument', '').strip()
                    quote = entry.get('quote', '').strip().lower()
                    if not arg: continue
                    
                    best_start = speaker_starts.get(orig_spk, 0)
                    if quote:
                        for s_seg in spk_segments:
                            if quote in s_seg['text'] or s_seg['text'] in quote:
                                best_start = s_seg['start']
                                break
                    
                    video_link = ''
                    if source_url:
                        ts = best_start + offset
                        base_url = source_url.split('?')[0].split('#')[0].rstrip('/')
                        if base_url.endswith('/0'): base_url = base_url[:-2]
                        video_link = f"{base_url}?ts={ts}"

                    if sentiment not in raw_args_pool: sentiment = "Unknown"
                    raw_args_pool[sentiment].append(arg)
                    if arg not in arg_to_speakers: arg_to_speakers[arg] = set()
                    arg_to_speakers[arg].add(spk)
                    if video_link:
                        if arg not in arg_to_links: arg_to_links[arg] = []
                        arg_to_links[arg].append((spk, video_link))
                    
        self._spinner_done()

        grouped_results = []
        for sentiment, raw_list in raw_args_pool.items():
            if not raw_list: continue
            clusters = self._cluster_by_embeddings(raw_list, sentiment)
            self._spinner_done()
            for cluster in clusters:
                canonical = cluster.get('canonical', '').replace('\n', ' ').strip()
                matches = cluster.get('raw_matches', [])
                if not canonical: continue
                cluster_speakers = set(); cluster_links = []; seen_urls = set()
                for match in matches:
                    cluster_speakers.update(arg_to_speakers.get(match, set()))
                    for label, url in arg_to_links.get(match, []):
                        if url not in seen_urls:
                            cluster_links.append((label, url)); seen_urls.add(url)
                if cluster_speakers:
                    grouped_results.append({'argument': canonical, 'count': len(cluster_speakers), 'sentiment': sentiment, 'links': cluster_links})
        
        # Improve date range extraction using more robust logic
        all_dates_clean = []
        for d in all_dates:
            try:
                # Basic cleaning for common parsing issues
                clean_d = d.replace('Sept ', 'Sep ').replace('Sept. ', 'Sep. ')
                all_dates_clean.append(clean_d)
            except: pass
        
        date_range = ""
        if all_dates_clean:
            # Sort dates to find the actual range
            def _parse(ds):
                for f in ['%b %d, %Y', '%B %d, %Y', '%Y-%m-%d', '%b. %d, %Y']:
                    try: return datetime.datetime.strptime(ds, f)
                    except: continue
                return datetime.datetime.min
            
            sorted_dates = sorted(all_dates_clean, key=_parse)
            if sorted_dates:
                date_range = f"From {sorted_dates[0]} to {sorted_dates[-1]}"
        
        categories = self.prompts.get('sentiment_categories', ['Neutral'])
        speaker_stats = {
            'total': len(speaker_sentiments),
            'categories': categories
        }
        for cat in categories:
            speaker_stats[cat] = 0
            
        for s in speaker_sentiments.values():
            for cat in categories:
                if cat in s or s in cat: 
                    speaker_stats[cat] += 1
                    break
            
        t = speaker_stats['total']
        for cat in categories:
            speaker_stats[f"pct_{cat}"] = (speaker_stats[cat] / t * 100) if t > 0 else 0
        
        self._generate_report(grouped_results, source_name, source_slug, date_range, speaker_stats)

    def _generate_report(self, results, source_name, source_slug, date_range, speaker_stats=None):
        if not results:
            self.log.error("No arguments extracted."); return
            
        results.sort(key=lambda x: x['count'], reverse=True)
        report_dir = self.fm.resolve_path('reports')
        mask_suffix = "-masked" if self.mask else ""
        
        out_file_md = os.path.join(report_dir, f"Semantic_Argument_Report-{source_slug}{mask_suffix}.md")
        with open(out_file_md, 'w') as f:
            f.write(f"# Semantic Argument Analysis - {source_name}\n\n")
            if date_range: f.write(f"**Time Period:** {date_range}\n\n")
            f.write(f"**Report Generated:** {datetime.datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n")
            if self.mask:
                f.write("Names have been anonymized for privacy.\n\n")
            if speaker_stats:
                f.write("### Speaker Statistics\n")
                f.write(f"- Total number of speakers (on-topic): {speaker_stats['total']}\n")
                
                for cat in speaker_stats.get('categories', []):
                    f.write(f"- Total Speakers {cat}: {speaker_stats.get(cat, 0)}\n")
                for cat in speaker_stats.get('categories', []):
                    f.write(f"- % {cat}: {speaker_stats.get(f'pct_{cat}', 0):.1f}%\n")
                f.write("\n")
            f.write("This report dynamically groups semantically similar arguments made by speakers into high-level canonical claims.\n\n")
            f.write("| Argument Made | Number of Speakers | Sentiment | Video Links |\n|---|---|---|---|\n")
            for res in results:
                links = res.get('links', []); md_links = ' '.join([f"[{label}]({url})" for label, url in links]) if links else '—'
                f.write(f"| {res['argument']} | {res['count']} | {res['sentiment']} | {md_links} |\n")
            f.write("\n---\n© Copyright 2026. Joel Greenberg. All Rights Reserved. Contact the author at joelontheroad@proton.me\n")
                
        self.log.success(f"Markdown Report generated: {out_file_md}")

        out_file_html = out_file_md.replace('.md', '.html')
        with open(out_file_html, 'w') as f:
            # Modern, High-End shared CSS
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
            .container { max-width: 1100px; margin: -2rem auto 4rem; padding: 0 1rem; }
            .dashboard {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 1.5rem;
                margin-bottom: 2rem;
            }
            .stat-card {
                background: var(--card-bg);
                padding: 1.5rem;
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
            
            table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.95rem; }
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
            
            .watch-btn {
                background: var(--primary);
                color: white;
                text-decoration: none;
                padding: 0.4rem 0.8rem;
                border-radius: 0.375rem;
                font-size: 0.75rem;
                font-weight: 600;
                transition: background 0.2s;
                display: inline-block;
                margin-right: 0.5rem;
                margin-bottom: 0.3rem;
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
            cats = speaker_stats.get('categories', ['Neutral']) if speaker_stats else ['Neutral']
            for i, cat in enumerate(cats):
                color = sentiment_colors[i % len(sentiment_colors)]
                slug = cat.lower().replace(' ', '-')
                pill_styles += f".pill-{slug} {{ background: {color['bg']}; color: {color['fg']}; }}\n            "
            if ".pill-neutral" not in pill_styles:
                pill_styles += ".pill-neutral { background: #f1f5f9; color: #475569; }\n            "
                
            style = style.replace("/* PILL_STYLES_PLACEHOLDER */", pill_styles)
            
            f.write(f"<!DOCTYPE html><html><head><title>Semantic Argument Analysis - {source_name}</title><style>{style}</style></head><body>")
            
            # Header
            f.write(f"<div class='header'>")
            f.write(f"<div class='meta'>SEMANTIC ARGUMENT CLUSTERING // GENESIS ANALYSIS</div>")
            f.write(f"<h1>{source_name}: Argument Landscape</h1>")
            f.write(f"<p style='opacity: 0.7; margin-top: 0.5rem; margin-bottom: 0;'>{date_range}</p>")
            f.write(f"<p style='opacity: 0.6; margin-top: 0.2rem; font-size: 0.9rem; font-family: monospace;'>Report Generated: {datetime.datetime.now().strftime('%B %d, %Y')}</p>")
            f.write(f"</div>")
            
            f.write("<div class='container'>")
            
            if self.mask:
                f.write("<div style='text-align: center; margin-bottom: 2rem; color: white; font-weight: bold;'>PRIVACY NOTICE: Names have been anonymized for privacy.</div>")

            # Dashboard
            total_args = len(results)
            top_sentiment = "N/A"
            if results:
                from collections import Counter
                top_sentiment = Counter([r['sentiment'] for r in results]).most_common(1)[0][0]

            f.write("<div class='dashboard'>")
            f.write(f"<div class='stat-card'><div class='label'>Total Arguments</div><div class='value'>{total_args}</div></div>")
            if speaker_stats:
                f.write(f"<div class='stat-card'><div class='label'>Total Speakers</div><div class='value'>{speaker_stats['total']}</div></div>")
                for cat in speaker_stats.get('categories', []):
                    count = speaker_stats.get(cat, 0)
                    pct = speaker_stats.get(f"pct_{cat}", 0)
                    f.write(f"<div class='stat-card'><div class='label'>{cat}</div><div class='value'>{count}<br><span style='font-size: 0.9rem; color: var(--text-muted); font-weight: 500;'>{pct:.1f}%</span></div></div>")
            f.write("</div>")
            
            f.write("<div class='content-section'>")
            f.write("<h2>Canonical Argument Clusters</h2>")
            f.write("<p style='color: var(--text-muted); margin-bottom: 1.5rem;'>The following table represents high-level semantic arguments grouped from individual speaker testimonies. Counts reflect the number of unique participants who made these points.</p>")
            
            f.write("<table><thead><tr><th>Core Argument Claim</th><th>Participant Count</th><th>Sentiment</th><th>Evidence Links</th></tr></thead><tbody>")
            for res in results:
                cat_pill = f"pill pill-{res['sentiment'].lower().replace(' ', '-')}"
                links = res.get('links', [])
                html_links = ''.join([f"<a href='{url}' target='_blank' class='watch-btn'>Watch Clip</a>" for l, url in links[:5]]) if links else '—'
                if len(links) > 5: html_links += f"<br><small style='color: var(--text-muted)'>+{len(links)-5} more links</small>"
                
                f.write(f"<tr>")
                f.write(f"<td><strong>{res['argument']}</strong></td>")
                f.write(f"<td>{res['count']} speakers</td>")
                f.write(f"<td><span class='{cat_pill}'>{res['sentiment']}</span></td>")
                f.write(f"<td>{html_links}</td>")
                f.write(f"</tr>")
            f.write("</tbody></table>")
            f.write("</div>")
            
            f.write("<div style='text-align: center; color: var(--text-muted); font-size: 0.8rem; padding: 2rem;'>")
            f.write("&copy; Copyright 2026. Joel Greenberg. All Rights Reserved. Contact the author at joelontheroad@proton.me")
            f.write("</div>")
            f.write("</div></body></html>")
            
        self.log.success(f"HTML Report generated: {out_file_html}")

def main():
    parser = argparse.ArgumentParser(description=None, usage="argument-analyzer.py [-h] [--mask] [--connector]", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mask', action='store_true', help='Mask speaker names')
    parser.add_argument('--connector', metavar='SLUG', help='Connector workspace')
    parser.add_argument('--list-connectors', action='store_true', help='List connectors')
    parser.add_argument('--about', action='store_true', help='Show program information')
    args = parser.parse_args()

    if args.about:
        print("\nArgument Analyzer")
        print("Part of the Speaker Analyzer collection of utilities to analyze speaker statements and intent on a subject of your choice, all done on a local GPU with local LLMs.\n")
        print("See --help and README.md for information on how to use this program.\n")
        print("© Copyright 2026. Joel Greenberg. All Rights Reserved. Contact the author at joelontheroad@proton.me")
        sys.exit(0)

    temp_fm = FileManager()
    available = get_available_connectors(Logger(verbose=False))
    
    if args.list_connectors:
        print("\nAvailable Source Connectors:"); print("-" * 30)
        for slug, cls in available.items(): print(f" {slug:<15} | {cls.DISPLAY_NAME}")
        print("-" * 30); sys.exit(0)

    slug = args.connector or temp_fm.config.get('default_connector', 'Austin')
    if slug not in available: print(f"Error: Unknown connector '{slug}'."); sys.exit(1)

    cls = available[slug]
    fm = FileManager(connector_slug=cls.SLUG)
    log = Logger(verbose=True, log_dir=fm.resolve_path('logs'))
    
    analyzer = ArgumentAnalyzer(log, fm, mask=args.mask)
    analyzer.run_pipeline(source_name=cls.DISPLAY_NAME, source_slug=cls.SLUG)
    
    elapsed = datetime.datetime.now() - start_time
    print(f"\nProgram ran for {elapsed.seconds//3600:02d}:{(elapsed.seconds//60)%60:02d}.")

if __name__ == "__main__": main()
