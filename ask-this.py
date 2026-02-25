#!/usr/bin/env ./.venv/bin/python3
# **********************************************************
# Public Meeting Speaker Analyzer
# file: ask-this.py
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

import os
import argparse
import requests
import chromadb
import re
import datetime

from utils.logger import Logger
from utils.file_manager import FileManager
from utils.preflight import Preflight
from utils.discovery import get_available_connectors

class KnowledgeQuery:
    def __init__(self, logger, file_manager):
        self.log = logger
        self.fm = file_manager
        
        self.api_url = self.fm.get_network_setting('llm_api_url') or "http://127.0.0.1:1234"
        rag_dir_setting = self.fm.get_ai_setting('rag', 'database_dir')
        self.rag_dir = rag_dir_setting if rag_dir_setting else self.fm.resolve_path('db')
        self.emb_model = self.fm.get_ai_setting('rag', 'embedding_model') or "nomic-embed-text-v1.5"
            
        if not os.path.exists(self.rag_dir):
            self.log.error(f"Vector Database not found at {self.rag_dir}")
            self.log.error("Please run ./knowledge-indexer.py first to ingest transcripts.")
            sys.exit(1)
            
        self.chroma_client = chromadb.PersistentClient(path=self.rag_dir)
        try:
            self.collection = self.chroma_client.get_collection(name="city_council")
        except ValueError:
             self.log.error("Collection 'city_council' not found in database. Please run ingestion first.")
             sys.exit(1)
             
        # Just to check if it's empty
        if self.collection.count() == 0:
             self.log.error("Database is empty. Please run ingestion first.")
             sys.exit(1)
             
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0

    def _get_spinner(self):
        char = self.spinner_chars[self.spinner_idx % len(self.spinner_chars)]
        self.spinner_idx += 1
        return char

    def _spinner_update(self, message):
        sys.stdout.write(f"\r[{self._get_spinner()}] {message}\033[K")
        sys.stdout.flush()

    def _spinner_done(self):
        print()

    def _get_embedding(self, text):
        url = f"{self.api_url.rstrip('/')}/v1/embeddings"
        payload = {
            "input": text,
            "model": self.emb_model
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                return data['data'][0]['embedding']
            else:
                self.log.error(f"Embedding failed ({resp.status_code}): {resp.text}")
                return None
        except Exception as e:
            self.log.error(f"Embedding Exception: {e}")
            return None

    def search(self, query_text, sentiment_filter=None):
        self._spinner_update("Embedding your question...")
        query_emb = self._get_embedding(query_text)
        if not query_emb:
            self._spinner_done()
            return None
            
        self._spinner_update("Searching semantic database...")
        
        query_args = {
            "query_embeddings": [query_emb],
            "n_results": 15
        }
        
        if sentiment_filter:
            query_args["where"] = {"sentiment": sentiment_filter}
            
        results = self.collection.query(**query_args)
        self._spinner_done()
        return results

    def _format_timestamp(self, ts):
        """Convert float seconds to HH:MM:SS"""
        hours, remainder = divmod(int(ts), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
    def _create_deep_link(self, source_url, ts):
        """Create a deep link if possible, depending on the source platform."""
        if 'youtube.com' in source_url or 'youtu.be' in source_url:
            sep = "&" if "?" in source_url else "?"
            return f"{source_url}{sep}t={int(ts)}s"
        elif 'swagit.com' in source_url:
            sep = "&" if "?" in source_url else "?"
            return f"{source_url}{sep}ts={int(ts)}"
        else:
            return source_url # Generic fallback

    def _get_answer_from_llm(self, question, search_results, mask=False):
        if not search_results or not search_results['documents'] or not search_results['documents'][0]:
             self.log.info("No documents returned from ChromaDB.")
             return None, None
             
        # DEBUG: Print retrieved snippets
        self.log.info(f"Retrieved {len(search_results['documents'][0])} snippets from database.")
        for i, doc in enumerate(search_results['documents'][0]):
            self.log.info(f"Snippet {i+1}: {doc[:100]}...")
             
        # Extract the top results
        docs = search_results['documents'][0]
        metas = search_results['metadatas'][0]
        
        context_snippets = []
        source_map = {} # Maps [Source N] -> Markdown/HTML formatted source info
        
        # --- Context Budgeting ---
        # Goal: Keep total context under LLM token limit (approx 4k tokens ~ 10-12k chars)
        MAX_CONTEXT_CHARS = 10000 
        current_context_chars = 0
        
        for i, (doc, meta) in enumerate(zip(docs, metas), 1):
            if current_context_chars >= MAX_CONTEXT_CHARS:
                break
                
            speaker = meta.get('speaker', 'Unknown')
            if mask and speaker != 'Unknown':
                # Generate a consistent pseudo-ID for this session
                speaker_hash = abs(hash(speaker)) % 10000
                speaker = f"Speaker #{speaker_hash:04d}"
                
            date = meta.get('date', 'Unknown')
            title = meta.get('title', 'Unknown Meeting')
            ts = meta.get('timestamp', 0)
            url = meta.get('source_url', '#')
            sentiment = meta.get('sentiment', 'Unknown Sentiment')
            
            deep_link = self._create_deep_link(url, ts)
            formatted_ts = self._format_timestamp(ts)
            
            # Smart Truncation: Give top results more room, then tighten as we go
            remaining_budget = MAX_CONTEXT_CHARS - current_context_chars
            if i <= 3:
                snippet_limit = min(3000, remaining_budget)
            elif i <= 8:
                snippet_limit = min(1500, remaining_budget)
            else:
                snippet_limit = min(800, remaining_budget)
                
            doc_snippet = doc[:snippet_limit]
            if len(doc) > snippet_limit:
                doc_snippet += "..."
                
            # For the LLM Prompt
            snippet_formatted = f"[CITARE-SOURCE-{i}] {speaker} [{sentiment}] on {date} (Time: {formatted_ts}):\n\"{doc_snippet}\""
            context_snippets.append(snippet_formatted)
            current_context_chars += len(snippet_formatted)
            
            # For our exact replacement map
            source_map[f"[CITARE-SOURCE-{i}]"] = {
                "name": speaker,
                "title": title,
                "date": date,
                "time": formatted_ts,
                "url": deep_link
            }
            
        context_block = "\n\n".join(context_snippets)
        
        system_prompt = f"""You are a helpful AI policy assistant answering questions about public meetings.
Use the provided context snippets to answer the user's question. The snippets are the closest semantic matches found in the database.

Identity & Roles:
1. If the user asks about a specific person (e.g., "Mayor Watson") and a snippet's speaker is a raw ID (e.g., "SPEAKER_01") but the context or metadata suggests they are fulfilling that role (e.g., presiding over the meeting, ruling people out of order, or being addressed as such), you SHOULD attribute the statement to that person.
2. If the speaker name is resolved to a role like "Mayor Kirk Watson" or "Chair Smith", treat them as the person in question even if the name is slightly different.

Rhetorical Analysis & Tone:
Carefully analyze the tone of each snippet. If a speaker is using irony, sarcasm, or using a term rhetorically (e.g., as a hostile polemic rather than a genuine expression of sympathy or support), that snippet does NOT represent a genuine viewpoint and should be excluded.

Citation Rules:
1. Every speaker you mention MUST have exactly one source bracket directly after the sentence, e.g. [CITARE-SOURCE-1]. No unlinked speakers are allowed.
2. DO NOT include the speaker's name, date, or time in your narrative answer text. Only use the citation tag. For example, instead of saying "John Doe said on March 5th...", say "The speaker argued that [CITARE-SOURCE-1]...".
3. Include any speaker whose statement relevantly addresses the user's question — even if they use different words.
4. Do not exclude a source unless it is genuinely and completely unrelated to the question. For procedural matters like "out of order" admonitions, report them factually without assuming hostile intent unless explicitly stated.
5. If truly zero sources are relevant, reply with only: "None of the speakers addressed this topic."
Do not create footnotes. Use inline brackets.

Context:
{context_block}
"""

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            "temperature": 0.2,
            "max_tokens": 1500
        }
        
        self._spinner_update("Generating answer...")
        
        try:
            url = f"{self.api_url.rstrip('/')}/v1/chat/completions"
            resp = requests.post(url, json=payload, timeout=120)
            self._spinner_done()
            if resp.status_code == 200:
                answer = resp.json()['choices'][0]['message']['content'].strip()
                return answer, source_map
            else:
                self.log.error(f"LLM Chat Error {resp.status_code}: {resp.text}")
                return None, None
        except Exception as e:
            self._spinner_done()
            self.log.error(f"LLM Exception: {e}")
            return None, None

    def post_process_and_output(self, raw_answer, source_map, is_separate, original_q, batch_timestamp, is_single_query, mask=False):
        if not raw_answer:
            print("\nNo answer generated.")
            return

        # Filter source_map to only include sources actually cited in the answer
        used_sources = {k: v for k, v in source_map.items() if k in raw_answer}

        # Prepare Markdown and HTML versions text with inline links
        final_text_md = raw_answer
        final_text_html = raw_answer

        for src_tag, details in used_sources.items():
            link_text = f"{details['name']} in {details['title']} ({details['date']}) @ {details['time']}"
            
            link_md = f"[{link_text}]({details['url']})"
            final_text_md = final_text_md.replace(src_tag, f" {link_md} ")
            
            link_html = f'<a href="{details["url"]}" target="_blank" class="citation" title="{details["title"]}">{link_text}</a>'
            final_text_html = final_text_html.replace(src_tag, f" <span>[{link_html}]</span> ")
                
        # Clean up double spaces
        final_text_md = final_text_md.replace("  ", " ").replace(" .", ".").replace(" ,", ",")
        final_text_html = final_text_html.replace("  ", " ").replace(" .", ".").replace(" ,", ",")

        if not is_single_query:
            # Always export both for batches
            self._export_markdown(original_q, final_text_md, used_sources, is_separate, batch_timestamp, mask=mask)
            self._export_html(original_q, final_text_html, used_sources, is_separate, batch_timestamp, mask=mask)
        
        # Also print to console for immediate feedback
        print("\n" + "="*60)
        print(f"Q: {original_q}")
        print("="*60 + "\n")
        print(final_text_md)
        print("\n### Verified Sources for Creating this Answer")
        if not used_sources:
            print("- No direct sources cited in the response.")
        for src_tag, det in used_sources.items():
            print(f"- {det['name']} in {det['title']} ({det['date']}) @ {det['time']} [{det['url']}]")
        print("\n" + "="*60 + "\n")

    def _export_markdown(self, query, md_answer, source_map, is_separate, batch_timestamp, mask=False):
        report_dir = self.fm.resolve_path('reports')
        os.makedirs(report_dir, exist_ok=True)
        
        mask_suffix = "-masked" if mask else ""
        if is_separate:
            clean_q = re.sub(r'[^a-zA-Z0-9]', '_', query)[:30]
            out_file = os.path.join(report_dir, f"RAG_Answer_{clean_q}{mask_suffix}.md")
            mode = 'w'
        else:
            out_file = os.path.join(report_dir, f"RAG_Batch_Report_{batch_timestamp}{mask_suffix}.md")
            mode = 'a'
            
        is_new_file = not os.path.exists(out_file) or mode == 'w'
            
        with open(out_file, mode, encoding='utf-8') as f:
            if is_new_file:
                f.write(f"# Knowledge Base Queries\n\n")
            
            f.write(f"## Q: {query}\n\n")
            f.write(f"{md_answer}\n\n")
            
            f.write("### Sources\n")
            for src_tag, det in source_map.items():
                f.write(f"- [{det['name']} in {det['title']} ({det['date']}) @ {det['time']}]({det['url']})\n")
                
            f.write("\n---\n")
            if is_separate:
                f.write("© Copyright 2026. Joel Greenberg. All Rights Reserved. Contact the author at joelontheroad@proton.me\n")
                self.log.success(f"Generated separate MD report: {out_file}")

    def _export_html(self, query, html_answer, source_map, is_separate, batch_timestamp, mask=False):
        report_dir = self.fm.resolve_path('reports')
        os.makedirs(report_dir, exist_ok=True)
        
        mask_suffix = "-masked" if mask else ""
        if is_separate:
            clean_q = re.sub(r'[^a-zA-Z0-9]', '_', query)[:30]
            out_file = os.path.join(report_dir, f"RAG_Answer_{clean_q}{mask_suffix}.html")
            mode = 'w'
        else:
            out_file = os.path.join(report_dir, f"RAG_Batch_Report_{batch_timestamp}{mask_suffix}.html")
            mode = 'a'
            
        is_new_file = not os.path.exists(out_file) or mode == 'w'
        
        style = """
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f8f9fa; color: #333; line-height: 1.6; margin: 0; padding: 40px; }
        .container { max-width: 800px; margin: auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }
        h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        .question { font-weight: bold; font-size: 1.2em; color: #e74c3c; margin-bottom: 20px; border-left: 4px solid #e74c3c; padding-left: 10px;}
        .answer { font-size: 1.05em; margin-bottom: 30px; white-space: pre-wrap; }
        .citation { color: #2980b9; text-decoration: none; font-weight: 500; font-size: 0.9em; }
        .citation:hover { text-decoration: underline; color: #1abc9c; }
        .footer { margin-top: 50px; text-align: center; font-size: 0.8em; color: #7f8c8d; border-top: 1px solid #ecf0f1; padding-top: 20px; }
        .sources-list { background: #fdfefe; border: 1px solid #bdc3c7; padding: 15px; border-radius: 5px; }
        """
        
        with open(out_file, mode, encoding='utf-8') as f:
            if is_new_file:
                f.write(f"<!DOCTYPE html><html><head><title>Council Knowledge Query</title><style>{style}</style></head><body>")
                
            f.write('<div class="container">')
            if is_new_file:
                f.write('<h1>Knowledge Base Query</h1>')
                
            f.write(f'<div class="question">Q: {query}</div>')
            f.write(f'<div class="answer">{html_answer}</div>')
            
            f.write('<div class="sources-list"><h3>Verified Sources for Creating this Answer</h3><ul>')
            for src_tag, det in source_map.items():
                f.write(f'<li><a href="{det["url"]}">{det["name"]} in {det["title"]} ({det["date"]}) @ {det["time"]}</a></li>')
            f.write('</ul></div>')
            
            if is_separate:
                f.write('<div class="footer">Generated by Semantic RAG Engine - &copy; Copyright 2026. Joel Greenberg. All Rights Reserved. Contact the author at joelontheroad@proton.me</div>')
            f.write('</div>') # end container
            
            if is_separate:
                f.write('</body></html>')
                self.log.success(f"Generated separate HTML report: {out_file}")

def main():
    epilog_text = """Notes:
  Allows user to ask ad hoc questions of knowledge base already downloaded and processed by speaker-analyzer.py
  Must run knowledge-indexer.py prior to using in order to configure knowledge base for ad hoc questions
  Can ask one question on the command line (--query). Answer is printed on the command line.
  Ask multiple questions by putting them in a text file and using --file flag. Answers are given in a report file.
  When asking multiple questions at once, the report groups all the answers together.  --separate splits them up so the answers are in their own files."""

    parser = argparse.ArgumentParser(
        description=None,
        usage="ask-this.py [-h] (-q QUERY | -f FILE) [--separate] [--mask] [--sentiment SENTIMENT]",
        epilog=epilog_text,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('-q', '--query', type=str, metavar='QUERY', help='The question you want to ask in quotes.')
    group.add_argument('-f', '--file', type=str, metavar='FILE', help='Path to a text file containing the question/prompt. Used in lieu of --query')
    parser.add_argument('--separate', action='store_true', help='Export each answer into its own separate file instead of appending them into a single report')
    parser.add_argument('--mask', action='store_true', help='Mask speaker names in reports and LLM prompts for privacy')
    parser.add_argument('--sentiment', type=str, metavar='SENTIMENT', help='Explicitly filter Vector DB search by a specific sentiment class, e.g., "Pro-proposition" or "Con-proposition"')
    parser.add_argument('--connector', metavar='SLUG', help='Specify which connector workspace to query (e.g., Austin, Houston)')
    parser.add_argument('--list-connectors', action='store_true', help='List all available connectors/cities and exit.')
    parser.add_argument('--about', action='store_true', help='Show program information')
    
    args = parser.parse_args()

    if args.about:
        print("\nAsk This (RAG Query Tool)")
        print("Part of the Speaker Analyzer collection of utilities to analyze speaker statements and intent on a subject of your choice, all done on a local GPU with local LLMs.\n")
        print("See --help and README.md for information on how to use this program.\n")
        print("© Copyright 2026. Joel Greenberg. All Rights Reserved. Contact the author at joelontheroad@proton.me")
        sys.exit(0)

    if args.list_connectors:
        from utils.discovery import get_available_connectors
        available = get_available_connectors(Logger(verbose=False))
        print("\nAvailable Source Connectors:")
        print("-" * 30)
        for slug, cls in available.items():
            print(f" {slug:<15} | {cls.DISPLAY_NAME}")
        print("-" * 30)
        sys.exit(0)

    if not args.query and not args.file:
        parser.error("one of the arguments -q/--query -f/--file is required (unless using --list-connectors)")

    fm = FileManager(connector_slug=args.connector)
    log_dir = fm.resolve_path('logs')
    log = Logger(verbose=True, log_dir=log_dir)
    
    # Optional preflight for LM Studio to ensure /v1/chat/completions works
    pf = Preflight(log, fm)
    if not pf.check_llm():
        log.error("Could not communicate with LLM API. Make sure LM Studio is running.")
        sys.exit(1)
        
    questions = []
    if args.query:
        if args.query.strip():
            questions.append(args.query.strip())
    elif args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                 # Read line by line, stripping whitespace, and ignoring empty lines
                 lines = f.readlines()
                 for line in lines:
                     cleaned = line.strip()
                     if cleaned:
                         questions.append(cleaned)
        except Exception as e:
            log.error(f"Failed to read file {args.file}: {e}")
            sys.exit(1)
            
    if not questions:
         log.error("No valid questions found.")
         sys.exit(1)

    kq = KnowledgeQuery(log, fm)
    
    batch_timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    
    for i, question in enumerate(questions, 1):
        if len(questions) > 1:
            pct = int((i / len(questions)) * 100)
            bar_len = 20
            filled = int(bar_len * i // len(questions))
            bar = '=' * filled + '-' * (bar_len - filled)
            print(f"\n[Processing {i}/{len(questions)}] [{bar}] {pct}%")
            
        search_results = kq.search(question, sentiment_filter=args.sentiment)
        if search_results:
             raw_ans, smap = kq._get_answer_from_llm(question, search_results, args.mask)
             if raw_ans:
                 is_single = len(questions) == 1
                 kq.post_process_and_output(raw_ans, smap, args.separate, question, batch_timestamp, is_single_query=is_single, mask=args.mask)
                 
    # If not separate, close out the appended HTML file (only for batches)
    if not args.separate and len(questions) > 1:
        report_dir = fm.resolve_path('reports')
        mask_suffix = "-masked" if args.mask else ""
        out_file_html = os.path.join(report_dir, f"RAG_Batch_Report_{batch_timestamp}{mask_suffix}.html")
        out_file_md = os.path.join(report_dir, f"RAG_Batch_Report_{batch_timestamp}{mask_suffix}.md")
        if os.path.exists(out_file_html):
            with open(out_file_html, 'a', encoding='utf-8') as f:
                f.write('<div class="footer">Generated by Semantic RAG Engine - &copy; Copyright 2026. Joel Greenberg. All Rights Reserved. Contact the author at joelontheroad@proton.me</div>')
                f.write('</body></html>')
            log.success(f"Generated Combined HTML Report: {out_file_html}")
        if os.path.exists(out_file_md):
            with open(out_file_md, 'a', encoding='utf-8') as f:
                f.write("© Copyright 2026. Joel Greenberg. All Rights Reserved. Contact the author at joelontheroad@proton.me\n")
            log.success(f"Generated Combined Markdown Report: {out_file_md}")

if __name__ == "__main__":
    main()
