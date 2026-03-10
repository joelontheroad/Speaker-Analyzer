#!/usr/bin/env python3
import os
import json
import glob
import argparse
from datetime import datetime

def setup_argparse():
    parser = argparse.ArgumentParser(description="Compile JSON transcripts into an LLM-digestible text corpus.")
    parser.add_argument("--connector", type=str, required=True, help="Workspace/Connector slug (e.g., Austin, Houston, YouTube)")
    parser.add_argument("--workspace-root", type=str, default="workspaces", help="Root directory for workspaces")
    parser.add_argument("--max-tokens", type=int, default=15000, help="Maximum estimated tokens per output file (default: 15,000 for local 12GB VRAM LLMs)")
    return parser.parse_args()

def estimate_tokens(text):
    # Rule of thumb: 1 token ~= 4 characters in English
    return len(text) // 4

def parse_date(date_str):
    if not date_str or date_str.lower() in ['unknown', 'unknown date']:
        return datetime.max
        
    clean_date = date_str.replace('Sept ', 'Sep ').replace('Sept. ', 'Sep. ')
    for fmt in ['%b %d, %Y', '%B %d, %Y', '%Y-%m-%d', '%b. %d, %Y', '%m/%d/%Y', '%m/%d/%y', '%Y%m%d']:
        try:
            return datetime.strptime(clean_date, fmt)
        except ValueError:
            continue
    return datetime.max

def build_corpus(workspace_path, max_tokens):
    transcripts_dir = os.path.join(workspace_path, "transcripts")
    output_dir = os.path.join(workspace_path, "corpus")
    
    if not os.path.exists(transcripts_dir):
        print(f"Error: Transcripts directory not found at {transcripts_dir}")
        return
        
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Gather and sort files by meeting date
    files = glob.glob(os.path.join(transcripts_dir, "*.json"))
    meeting_data = []
    
    for f in files:
        try:
            with open(f, 'r') as jf:
                data = json.load(jf)
                meeting_date = data.get("metadata", {}).get("date", "Unknown Date")
                meeting_data.append({
                    "file": f,
                    "date": meeting_date,
                    "sort_key": parse_date(meeting_date),
                    "data": data
                })
        except Exception as e:
            print(f"Failed to read {f}: {e}")
            
    meeting_data.sort(key=lambda x: x["sort_key"])
    
    print(f"Found {len(meeting_data)} transcripts. Building corpus chunks (Max {max_tokens} tokens/file)...")
    
    # 2. Extract and chunk text
    current_chunk = 1
    current_tokens = 0
    current_content = []
    
    def save_chunk():
        nonlocal current_chunk, current_content, current_tokens
        if not current_content: return
        
        out_file = os.path.join(output_dir, f"Corpus_Part{current_chunk:02d}.md")
        with open(out_file, 'w') as out:
            out.write("\n".join(current_content))
            
        print(f"  -> Saved {out_file} (~{current_tokens} tokens)")
        
        current_chunk += 1
        current_tokens = 0
        current_content = []
        
        # Add a fresh header to the new file to maintain LLM context
        current_content.append(f"# Public Meeting Transcripts Corpus (Part {current_chunk})\n")
        current_content.append("CONTINUED FROM PREVIOUS PART...\n\n")

    # Start first file header
    current_content.append(f"# Public Meeting Transcripts Corpus (Part {current_chunk})\n")
    current_content.append("The following are chronologically ordered transcripts of public meetings. Each entry denotes the meeting metadata followed by the exact timecode and speaker for every statement.\n\n")

    for meeting in meeting_data:
        data = meeting["data"]
        meta = data.get("metadata", {})
        title = meta.get("title", "Unknown Meeting")
        date_str = meeting["date"]
        
        meeting_header = f"## MEETING: {title}\n**Date:** {date_str}\n\n"
        meeting_tokens = estimate_tokens(meeting_header)
        
        # If just the header pushes us over, save first
        if current_tokens + meeting_tokens > max_tokens and current_tokens > 0:
            save_chunk()
            
        current_content.append(meeting_header)
        current_tokens += meeting_tokens
        
        # We need to determine who is speaking at what time.
        # WhisperX provides 'segments', and often speaker diarization.
        # We will parse out the text and prefix it with the speaker and time.
        for segment in data.get("segments", []):
            speaker = segment.get("speaker", "UNKNOWN_SPEAKER")
            text = segment.get("text", "").strip()
            start_time = segment.get("start", 0.0)
            
            # Formatting time (e.g., 65.5 -> 01:05)
            mins = int(start_time // 60)
            secs = int(start_time % 60)
            time_str = f"[{mins:02d}:{secs:02d}]"
            
            line = f"**{speaker}** {time_str}: {text}\n"
            line_tokens = estimate_tokens(line)
            
            # Word wrap the chunk if it gets too large inside a single meeting
            if current_tokens + line_tokens > max_tokens and current_tokens > 0:
                save_chunk()
                # Re-add meeting header context for the LLM
                current_content.append(f"*(Continuing Meeting: {title} on {date_str})*\n\n")
            
            current_content.append(line)
            current_tokens += line_tokens
            
        current_content.append("\n---\n\n")

    # Save any remaining content in the buffer
    if current_content:
        save_chunk()

    print(f"\nSuccess! Corpus compiled into {current_chunk - 1} parts in '{output_dir}'.")
    print("You can now load these individual .md files directly into LM Studio as context.")

if __name__ == "__main__":
    args = setup_argparse()
    
    import yaml
    
    workspace_root = args.workspace_root
    try:
        with open('configs/defaults.yaml', 'r') as f:
            cfg = yaml.safe_load(f)
            workspace_root = cfg.get('paths', {}).get('workspace_root', 'workspaces')
    except Exception as e:
        print(f"Warning: Could not read configs/defaults.yaml: {e}")
        
    workspace_path = os.path.join(workspace_root, args.connector)
        
    print(f"Compiling Corpus for connector: {args.connector}")
    print(f"Workspace path: {workspace_path}")
    
    build_corpus(workspace_path, args.max_tokens)
