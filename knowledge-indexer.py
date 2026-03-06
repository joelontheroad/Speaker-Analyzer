#!/usr/bin/env ./.venv/bin/python3
# **********************************************************
# Public Meeting Speaker Analyzer
# file: knowledge-indexer.py
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
import json
import requests
import datetime
import argparse
import chromadb

from utils.logger import Logger
from utils.file_manager import FileManager
from utils.preflight import Preflight
from utils.discovery import get_available_connectors

start_time = datetime.datetime.now()
print(f"Starting Knowledge Indexer at {start_time.strftime('%I:%M %p %Y-%m-%d')}...")

class KnowledgeIndexer:
    def __init__(self, logger, file_manager):
        self.log = logger
        self.fm = file_manager
        
        self.api_url = self.fm.get_network_setting('llm_api_url') or "http://127.0.0.1:1234"
        rag_dir_setting = self.fm.get_ai_setting('rag', 'database_dir')
        self.rag_dir = rag_dir_setting if rag_dir_setting else self.fm.resolve_path('db')
        self.emb_model = self.fm.get_ai_setting('rag', 'embedding_model') or "nomic-embed-text-v1.5"
        self.chunk_size = int(self.fm.get_ai_setting('rag', 'chunk_size') or 500)
            
        self.log.info(f"Using RAG database in: {self.rag_dir}")
        self.log.info(f"Connector Slug: {self.fm.connector_slug}")
        self.log.info(f"Transcripts Path Resolved: {self.fm.resolve_path('transcripts')}")
        os.makedirs(self.rag_dir, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=self.rag_dir)
        self.collection = self.chroma_client.get_or_create_collection(name="city_council")

        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0

    def _get_spinner(self):
        char = self.spinner_chars[self.spinner_idx % len(self.spinner_chars)]
        self.spinner_idx += 1
        return char

    def _spinner_update(self, message):
        # \033[K clears to the end of the line to prevent trailing "ghost" characters
        sys.stdout.write(f"\r[{self._get_spinner()}] {message}\033[K")
        sys.stdout.flush()

    def _spinner_done(self):
        print()

    def _get_embedding(self, text):
        url = f"{self.api_url.rstrip('/')}/v1/embeddings"
        
        # Add Nomic embedding prefix for indexing
        prefixed_text = f"search_document: {text}"
        
        payload = {
            "input": prefixed_text,
            "model": self.emb_model
        }
        try:
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                return data['data'][0]['embedding']
            else:
                self.log.error(f"Embedding failed ({resp.status_code}): {resp.text}")
                return None
        except Exception as e:
            self.log.error(f"Embedding Exception: {e}")
            return None

    def _chunk_segments(self, segments, metadata_template, speaker_sentiments):
        """
        Groups segments by speaker and chunks them into max ~chunk_size words.
        Returns a list of dicts: {'id': str, 'text': str, 'metadata': dict}
        """
        chunks = []
        current_speaker = None
        current_text = []
        current_word_count = 0
        current_start_time = 0
        
        chunk_index = 0
        
        def finalize_chunk():
            nonlocal chunk_index, current_text, current_word_count
            if not current_text: return
            
            raw_text_str = " ".join(current_text)
            if current_word_count > 2: # Lowered from 10 to catch short interjections like "Out of order"
                meta = metadata_template.copy()
                
                # Resolve name and sentiment from manifest
                speaker_info = speaker_sentiments.get(current_speaker, {})
                speaker_name = speaker_info.get('name', current_speaker or 'Unknown')
                
                meta['speaker'] = speaker_name
                meta['sentiment'] = speaker_info.get('sentiment', 'Unknown')
                
                meta['timestamp'] = current_start_time + meta.get('offset', 0)
                
                if 'offset' in meta:
                    del meta['offset']
                    
                contextual_text = f"Speaker {speaker_name} said: {raw_text_str}"
                
                chunks.append({
                    'id': f"{meta['video_id']}_{chunk_index}",
                    'text': contextual_text,
                    'metadata': meta
                })
                chunk_index += 1
                
            current_text = []
            current_word_count = 0

        for seg in segments:
            speaker = seg.get('speaker', 'Unknown')
            text = seg.get('text', '').strip()
            if not text: continue
            
            words = len(text.split())
            
            # If speaker changed OR chunk is too big, finalize current chunk
            if speaker != current_speaker or (current_word_count + words > self.chunk_size):
                finalize_chunk()
                current_speaker = speaker
                current_start_time = float(seg.get('start', 0.0))
            elif not current_text:
                current_speaker = speaker
                current_start_time = float(seg.get('start', 0.0))
                
            current_text.append(text)
            current_word_count += words
            
        finalize_chunk()
        return chunks

    def run_indexing(self, force=False):
        trans_dir = self.fm.resolve_path('transcripts')
        if not trans_dir or not os.path.exists(trans_dir):
            self.log.error("Transcripts directory not found. Please run speaker-analyzer first to generate data.")
            sys.exit(1)

        files = [f for f in os.listdir(trans_dir) if f.endswith('_transcript.json')]
        if not files:
            all_files = os.listdir(trans_dir)
            self.log.error(f"No transcript files found in: {trans_dir}")
            self.log.info(f"Directory contains {len(all_files)} files total.")
            if all_files:
                self.log.info(f"Sample files: {all_files[:3]}")
            sys.exit(1)
            
        total_files = len(files)
        total_chunks_added = 0
        
        for i, f_name in enumerate(files, 1):
            vid_id = f_name.replace('_transcript.json', '')
            trans_path = os.path.join(trans_dir, f_name)
            summaries_dir = self.fm.resolve_path('summaries')
            meta_path = os.path.join(summaries_dir, f"{vid_id}_metadata.json")
            
            # Load basic metadata
            source_url = "Unknown"
            date = "Unknown"
            title = "Unknown"
            offset = 0
            
            if os.path.exists(meta_path):
                with open(meta_path, 'r') as f:
                    m = json.load(f)
                    source_url = m.get('source_url', 'Unknown')
                    date = m.get('date', 'Unknown')
                    title = m.get('title', 'Unknown')
                    offset = m.get('offset', 0)
                    
            # Load sentiment manifest if it exists
            speaker_sentiments = {}
            manifest_path = os.path.join(summaries_dir, f"{vid_id}_speakers.json")
            if os.path.exists(manifest_path):
                with open(manifest_path, 'r') as f:
                    speaker_sentiments = json.load(f)
            
            # Check if this file is already in ChromaDB (unless forced)
            if not force:
                existing = self.collection.get(where={"video_id": vid_id}, limit=1)
                if existing and existing['ids']:
                    self.log.info(f"Skipping {vid_id} - already indexed.")
                    continue
            else:
                # Delete existing entries for this video if forcing
                self.collection.delete(where={"video_id": vid_id})
                self.log.info(f"Re-indexing {vid_id} (forced)...")

            with open(trans_path, 'r') as f:
                data = json.load(f)
                
            segments = data.get('segments', [])
            if not segments: continue
            
            metadata_template = {
                'video_id': vid_id,
                'source_url': source_url,
                'date': str(date),
                'title': str(title),
                'offset': int(offset)
            }
            
            self._spinner_update(f"[{i}/{total_files}] Chunking {vid_id}...")
            chunks = self._chunk_segments(segments, metadata_template, speaker_sentiments)
            
            if not chunks: continue
            
            # Embed and upsert in batches to avoid overwhelming the local API/RAM
            ids = []
            embeddings = []
            metadatas = []
            documents = []
            
            for c_idx, chunk in enumerate(chunks, 1):
                # Calculate percentage for progress indicator
                pct = int((c_idx / len(chunks)) * 100)
                
                # Build a simple visual progress bar [====>   ]
                bar_len = 20
                filled = int(bar_len * c_idx // len(chunks))
                bar = '=' * filled + '-' * (bar_len - filled)
                
                self._spinner_update(f"[{i}/{total_files}] Embedding {vid_id}: [{bar}] {pct}% ({c_idx}/{len(chunks)} chunks)")
                emb = self._get_embedding(chunk['text'])
                
                if emb:
                    ids.append(chunk['id'])
                    embeddings.append(emb)
                    metadatas.append(chunk['metadata'])
                    documents.append(chunk['text'])
                    
            if ids:
                self._spinner_update(f"[{i}/{total_files}] Saving {len(ids)} chunks to Vector DB...")
                self.collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    metadatas=metadatas,
                    documents=documents
                )
                total_chunks_added += len(ids)

        self._spinner_done()
        self.log.success(f"Ingestion complete! Added {total_chunks_added} new chunks to the database.")

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Knowledge Indexer - RAG Ingestion Pipeline.\n\n"
            "You have created a valuable knowledge base by using speaker-analyzer.py.  You can query the\n"
            "knowledge base by using ask-this.py, but before you do, run this program in order to technically\n"
            "prepare the knowledge base. You only need to run once after a report has been created by\n"
            "speaker-analyzer.py.  No need to re-run it unless you've downloaded more media."
        ),
        usage="knowledge-indexer.py [-h]",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--force', action='store_true', help='Re-index all files, overwriting existing database entries')
    parser.add_argument('--connector', metavar='SLUG', help='Specify which connector workspace to index (e.g., Austin, Houston)')
    parser.add_argument('--list-connectors', action='store_true', help='List all available connectors/cities and exit.')
    parser.add_argument('--about', action='store_true', help='Show program information')
    args = parser.parse_args()

    if args.about:
        print("\nKnowledge Indexer")
        print("Part of the Speaker Analyzer collection of utilities to analyze speaker statements and intent on a subject of your choice, all done on a local GPU with local LLMs.\n")
        print("See --help and README.md for information on how to use this program.\n")
        print("© Copyright 2026. Joel Greenberg. All Rights Reserved. Contact the author at joelontheroad@proton.me")
        sys.exit(0)

    # Discovery Parity
    temp_fm = FileManager()
    available_connectors = get_available_connectors(Logger(verbose=False))
    
    if args.list_connectors:
        print("\nAvailable Source Connectors:")
        print("-" * 30)
        for slug, cls in available_connectors.items():
            print(f" {slug:<15} | {cls.DISPLAY_NAME}")
        print("-" * 30)
        sys.exit(0)

    fm = FileManager(connector_slug=args.connector)
    log_dir = fm.resolve_path('logs')
    log = Logger(verbose=True, log_dir=log_dir)
    
    # Optional preflight for LM Studio to ensure /v1/embeddings isn't totally dead
    pf = Preflight(log, fm)
    if not pf.check_llm():
        log.error("Could not communicate with LLM API. Make sure LM Studio is running before indexing.")
        sys.exit(1)
        
    indexer = KnowledgeIndexer(log, fm)
    indexer.run_indexing(force=args.force)
    
    end_time = datetime.datetime.now()
    elapsed = end_time - start_time
    hours, remainder = divmod(elapsed.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    print(f"\nIndexing ran for {hours:02d}:{minutes:02d}  (Hours:Minutes).")

if __name__ == "__main__":
    main()
