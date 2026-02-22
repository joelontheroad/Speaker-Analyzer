#!/usr/bin/env ./.venv/bin/python3
# **********************************************************
# Public Meeting Speaker Analyzer
# file: speaker-analyzer.py
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
import argparse, re, os
import datetime

start_time = datetime.datetime.now()
print(f"Starting Program at {start_time.strftime('%I:%M %p %Y-%m-%d')}...")

from utils.logger import Logger
from utils.file_manager import FileManager
from utils.preflight import Preflight
from utils.extractor import Extractor
from utils.analyzer import Analyzer
from utils.discovery import get_available_connectors


class CustomArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print(f"\nError: {message}")
        print("\nWrong syntax on the command line.")
        self.print_help()
        sys.exit(1)

def print_status_report(stats, args, total_urls, processed_files=None, zero_results_files=None):
    """Print end-of-run status report based on flags used"""
    print("\n" + "="*52)
    print("STATUS REPORT: Files Processed")
    print("="*52)
    
    if args.all and args.force:
        # --all --force
        print(f"Downloaded:          {stats['downloaded']}")
        print(f"Transcribed:         {stats['transcribed']}")
        print(f"Total reported upon: {stats['reported']}")
    elif args.all:
        # --all (without force)
        print(f"Downloaded:          {stats['downloaded']}")
        print(f"Existing")
        print(f"(Not downloaded):    {stats['existing_media']}")
        print(f"Transcribed:         {stats['transcribed']}")
        print(f"Existing")
        print(f"(Not transcribed):   {stats['existing_transcripts']}")
        print(f"Total reported upon: {stats['reported']}")
    elif args.transcribe:
        # --transcribe
        print(f"Transcribed:      {stats['transcribed']}")
        print(f"Existing")
        print(f"(not transcribed): {stats['existing_transcripts']}")
        total_available = stats['transcribed'] + stats['existing_transcripts']
        print(f"Total available:  {total_available}")
    elif args.report:
        # --report
        print(f"Total new files processed:              {total_urls}")
        print(f"Total files used to generate final reports: {stats['reported']}")
    elif args.video or (args.audio and not args.transcribe and not args.report):
        # --audio or --video (download only)
        print(f"Downloaded:       {stats['downloaded']}")
        print(f"Existing")
        print(f"(not downloaded): {stats['existing_media']}")
        total_available = stats['downloaded'] + stats['existing_media']
        print(f"Total available:  {total_available}")
    
    print("="*52)
    
    # List files with no relevant comments
    if zero_results_files:
        print("\nAnalyzed but excluded (0 relevant comments):")
        for f in sorted(zero_results_files):
            print(f"  - {f}")
    
    # Verbose output - list all processed files
    if args.verbose and processed_files:
        print("\nProcessed Transcripts:")
        for f in sorted(processed_files):
            print(f"  - {f}")
        print()

def main():

    # parser = argparse.ArgumentParser(description="City Council Meeting Speaker Analyzer", add_help=False, usage=argparse.SUPPRESS) # Removed dead code
    
    epilog_text = """Notes:
  The source of truth for all paths is configs/defaults.yaml. 
  The LLM prompt and keywords are in configs/prompts.yaml.
  See README.md and DEPLOYMENT.md for technical requirements.
  Software provide as-is. No warranty expressed nor implied."""

    parser = CustomArgumentParser(
        description=None,
        usage="speaker-analyzer.py  --url URL | --batch textfile  [options...]",
        epilog=epilog_text,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True
    )
    
    # Input Options
    parser.add_argument("--url", metavar="URL", help="Download the media in the URL")
    parser.add_argument("--batch", metavar="textfile", help='Download all the media in a text file. "#" is a comment.')
    
    # Connector/City Selection
    parser.add_argument("--connector", metavar="SLUG", help="Specify which city or source connector to use (e.g., Austin, Houston). Optional when --url is provided (autodetects city from URL). Acts as override or for non-URL phases.")
    parser.add_argument("--list-connectors", action="store_true", help="List all available connectors/cities and exit.")
    
    # Phase Flags
    parser.add_argument("--audio", action="store_true", default=True, help="(Default) Download only audio and exit.")
    parser.add_argument("--video", action="store_true", help="Download video and audio and exit")
    parser.add_argument("--transcribe", action="store_true", help="Only transcribe the text from the audio and then exit. Reports if there are no media files to transcribe.")
    parser.add_argument("--report", action="store_true", help="Generate final report only. Reports if there are no transcriptions.")
    parser.add_argument("--all", action="store_true", default=False, help="(Default). Go through all phases in order: download media, transcribe, report.")
    
    # Context Flags
    parser.add_argument("--force", action="store_true", help="Force overwriting files. Program default is not to overwrite existing files")
    parser.add_argument('--mask', action='store_true', help="Mask speaker names in reports for privacy")
    parser.add_argument('--english', action='store_true', help="Force Whisper to translate non-English audio into English during transcription.")
    parser.add_argument('--verbose', action='store_true', help="Show detailed output including list of processed files")
    parser.add_argument('--about', action='store_true', help="Show program information and exit.")

    # Report Subset Flags (used with --report)
    parser.add_argument('--first', metavar='N', type=int, help="Report on only the first N meetings (chronologically). Use with --report.")
    parser.add_argument('--last', metavar='N', type=int, help="Report on only the last N meetings (chronologically). Use with --report.")
    parser.add_argument('--between', metavar='N-Y', type=str, help="Report on meetings N through Y inclusive, e.g. --between 3-7 or --between 3,7. Use with --report.")

    # Note: -h/--help is added automatically by add_help=True

    args = parser.parse_args()

    if args.about:
        print("\nPublic Meeting Speaker Analyzer")
        print("Part of the Speaker Analyzer collection of utilities to analyze speaker statements and intent on a subject of your choice, all done on a local GPU with local LLMs.\n")
        print("See --help and README.md for information on how to use this program.\n")
        print("© Copyright 2026. Joel Greenberg. All Rights Reserved. Contact the author at joelontheroad@proton.me")
        sys.exit(0)

    # Connector Discovery & Initialization
    temp_fm = FileManager()
    temp_log = Logger(verbose=args.verbose)
    available_connectors = get_available_connectors(temp_log)
    
    if args.list_connectors:
        print("\nAvailable Source Connectors:")
        print("-" * 30)
        for slug, cls in available_connectors.items():
            print(f" {slug:<15} | {cls.DISPLAY_NAME}")
        print("-" * 30)
        sys.exit(0)

    # Resolve Connector
    connector_slug = args.connector
    
    # Automatic Detection if URL is provided and slug is missing
    if not connector_slug and args.url:
        temp_log.info(f"Detecting city for URL: {args.url}")
        for slug, cls in available_connectors.items():
            try:
                if cls.can_handle(args.url):
                    connector_slug = slug
                    temp_log.info(f"Autodetected connector: {slug}")
                    break
            except Exception:
                continue
    
    if not connector_slug:
        connector_slug = temp_fm.config.get('default_connector')
    
    if not connector_slug:
        print("Error: No connector specified. Use --connector [SLUG] or set default_connector in config.")
        print("Run with --list-connectors to see available options.")
        sys.exit(1)
        
    if connector_slug not in available_connectors:
        print(f"Error: Unknown connector '{connector_slug}'.")
        print("Run with --list-connectors to see available options.")
        sys.exit(1)
        
    # Re-initialize everything with the correct connector workspace
    connector_class = available_connectors[connector_slug]
    source_name = connector_class.DISPLAY_NAME
    source_slug = connector_class.SLUG
    
    fm = FileManager(connector_slug=source_slug)
    log_dir = fm.resolve_path('logs')
    analysis_log_dir = os.path.join(log_dir, 'analysis')
    log = Logger(verbose=args.verbose, log_dir=analysis_log_dir)
    pre = Preflight(log, fm)
    
    print(f"Workspace: {source_slug} ({source_name})")
    
    if not pre.run_checks():
        sys.exit(1)
    
    ext = Extractor(log, fm, pre.get_hw())
    analyzer = Analyzer(log, fm)

    run_download = False
    run_transcribe = False
    run_report = False

    if args.all:
        run_download = True
        run_transcribe = True
        run_report = True
    else:
        # Check individual flags (allow combining phases)
        if args.transcribe:
            run_transcribe = True
        if args.report:
            run_report = True
        
        # If no specific phase flags provided, default to download if input exists
        if not (run_transcribe or run_report):
            if args.url or args.batch:
                 run_download = True
            else:
                print("Error: No action specified. Use --all, --transcribe, --report, or provide --url/--batch.")
                sys.exit(1)

    # Audio/Video preference (Phase 1)
    audio_only = not args.video # Default is True, unless --video

    # Collect URLs
    urls = []
    if args.url: urls.append(args.url)
    if args.batch and os.path.exists(args.batch):
        with open(args.batch, 'r') as f:
            urls.extend([line.strip() for line in f if line.strip() and not line.startswith('#')])
    
    # Statistics tracking
    stats = {
        'downloaded': 0,
        'existing_media': 0,
        'transcribed': 0,
        'existing_transcripts': 0,
        'reported': 0
    }
    
    # Track processed files for verbose output
    processed_transcript_files = []
    # Track files with zero relevant comments
    zero_results_files = []

    # PHASE 1: DOWNLOAD
    media_map = {} # Store video_id -> path mapping for next phases
    if run_download:
        print("\nInitiating Phase 1: Downloading")
        if not urls:
            print("Error: Phase 1 requires --url or --batch")
            sys.exit(1)
            
        for i, url in enumerate(urls, 1):
            if len(urls) > 1: print(f"\n[Batch Item {i}/{len(urls)}]")
            
            # Simple ID generation/extraction
            # Ideally Connectors should handle ID extraction too, but Extractor expects manifest.
            # We can use a hash or try to extract ID from URL.
            # Let's use a simple heuristic matching the current codebase's logic if possible,
            # or just use a safe slug from the URL.
            match = re.search(r'(?:videos|play)/(\d+)', url)
            vid_id = match.group(1) if match else f"vid_{abs(hash(url))}"
            
            manifest = {
                'video_id': vid_id, 
                'source_url': url,
                'audio_only': audio_only
            }
            
            # Check if file already exists BEFORE download attempt
            media_path = os.path.join(fm.resolve_path('media'), f"{vid_id}_audio.mp3")
            file_existed = os.path.exists(media_path)
            
            path, meta = ext.run_acquisition(manifest, force=args.force)
            if path:
                # Track statistics
                if file_existed and not args.force:
                    stats['existing_media'] += 1
                else:
                    stats['downloaded'] += 1
                media_map[vid_id] = path
                print(f"--- Acquired: {meta.get('title', 'Unknown')} ---")

    # PHASE 2: TRANSCRIBE
    transcript_map = {}
    if run_transcribe:
        print("\nInitiating Phase 2: Transcribing")
        # If we just ran download, we have media_map.
        # If we didn't, we need to find media files.
        # But we don't know which ones unless we scan or use the URLs provided?
        # "Run Phase 2 only... assumes media files exist".
        # If URLs provided, we assume we process those IDs.
        
        target_ids = list(media_map.keys())
        if not target_ids and urls:
             # Re-derive IDs from URLs
             for url in urls:
                match = re.search(r'(?:videos|play)/(\d+)', url)
                vid_id = match.group(1) if match else f"vid_{abs(hash(url))}"
                target_ids.append(vid_id)
        
        if not target_ids:
             # Scan media directory for all audio files
             media_dir = fm.resolve_path('media')
             if os.path.exists(media_dir):
                 for f in os.listdir(media_dir):
                     if f.endswith('_audio.mp3'):
                         # Extract vid_id
                         vid_id = f.replace('_audio.mp3', '')
                         target_ids.append(vid_id)

        for i, vid_id in enumerate(target_ids, 1):
            if len(target_ids) > 1: print(f"\n[Transcription {i}/{len(target_ids)}]")
            # Check if transcript already exists BEFORE transcription attempt
            trans_path = os.path.join(fm.resolve_path('transcripts'), f"{vid_id}_transcript.json")
            file_existed = os.path.exists(trans_path)
            
            trans_file = ext.run_transcription(vid_id, force=args.force, translate_to_english=args.english)
            if trans_file:
                # Track statistics
                if file_existed and not args.force:
                    stats['existing_transcripts'] += 1
                else:
                    stats['transcribed'] += 1
                transcript_map[vid_id] = trans_file

    # PHASE 3: REPORT
    if run_report:
        # Pre-flight check: Ensure LLM is available for reporting/analysis
        if not pre.check_llm_availability(enforce=True):
            sys.exit(1)

        # Similarly, use transcript_map or derive from targets
        target_ids = list(transcript_map.keys())
        if not target_ids and urls:
             for url in urls:
                match = re.search(r'(?:videos|play)/(\d+)', url)
                vid_id = match.group(1) if match else f"vid_{abs(hash(url))}"
                # Check if transcript exists
                possible_path = os.path.join(fm.resolve_path('transcripts'), f"{vid_id}_transcript.json")
                if os.path.exists(possible_path):
                    target_ids.append(vid_id)
        
        if not target_ids:
             # Scan transcripts directory for all available transcripts
             trans_dir = fm.resolve_path('transcripts')
             if os.path.exists(trans_dir):
                 for f in os.listdir(trans_dir):
                     if f.endswith('_transcript.json'):
                         # Extract vid_id
                         vid_id = f.replace('_transcript.json', '')
                         target_ids.append(vid_id)
        
        # Sort all target_ids chronologically by their meeting date from _metadata.json
        import json as _json
        summaries_dir = fm.resolve_path('summaries')
        def _get_meeting_date(vid_id):
            meta_path = os.path.join(summaries_dir, f"{vid_id}_metadata.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path) as _f:
                        return _json.load(_f).get('date', '')
                except Exception:
                    pass
            return ''
        target_ids.sort(key=_get_meeting_date)

        # Apply meeting range filters (--first, --last, --between)
        subset_flags = [args.first, args.last, args.between]
        if sum(f is not None and f is not False for f in subset_flags) > 1:
            print("Error: --first, --last, and --between are mutually exclusive. Use only one.")
            sys.exit(1)

        if args.first is not None:
            target_ids = target_ids[:args.first]
            print(f"[Filter] --first {args.first}: reporting on meetings 1–{len(target_ids)} of the full list.")
        elif args.last is not None:
            target_ids = target_ids[-args.last:]
            print(f"[Filter] --last {args.last}: reporting on the last {len(target_ids)} meetings.")
        elif args.between is not None:
            raw = args.between.replace(',', '-')
            parts = raw.split('-')
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                print("Error: --between requires two integers, e.g. --between 3-7 or --between 3,7")
                sys.exit(1)
            n, y = int(parts[0]), int(parts[1])
            if n < 1 or y < n:
                print("Error: --between N-Y requires N >= 1 and Y >= N")
                sys.exit(1)
            target_ids = target_ids[n - 1:y]  # convert to 0-indexed, inclusive
            print(f"[Filter] --between {n}-{y}: reporting on meetings {n}–{min(y, len(target_ids) + n - 1)}.")

        # Print phase header with count
        print(f"\nInitiating Phase 3: Reporting. Analyzing {len(target_ids)} transcripts.")
        
        if not target_ids:
            print("No transcripts found to report on.")
        
        all_results = []
        processed_meeting_dates = []  # Track dates of ALL processed meetings
        all_meetings_metadata = []    # Track metadata for ALL meetings (for table)
        grand_total_speakers = 0
        
        for i, vid_id in enumerate(target_ids, 1):
            if len(target_ids) > 1: print(f"\n[Reporting {i}/{len(target_ids)}]")
            trans_path = os.path.join(fm.resolve_path('transcripts'), f"{vid_id}_transcript.json")
            if os.path.exists(trans_path):
                # Count existing transcripts for stats
                stats['existing_transcripts'] += 1
                # Track for verbose output
                processed_transcript_files.append(f"{vid_id}_transcript.json")
                
                # run_analysis now returns (results, total_speakers_in_file, meeting_date, meeting_title)
                # Pass file progress indices
                results, file_total_speakers, meeting_date, meeting_title = analyzer.run_analysis(trans_path, mask=args.mask, file_index=i, total_files=len(target_ids))
                grand_total_speakers += file_total_speakers
                processed_meeting_dates.append(meeting_date)
                
                # New metadata collection
                all_meetings_metadata.append({
                    'meeting': meeting_title,
                    'date': meeting_date,
                    'has_on_topic': bool(results)
                })
                
                if not results:
                    zero_results_files.append(f"{vid_id}_transcript.json")
                all_results.extend(results)
        
        if processed_transcript_files: # Generate report if ANY files processed, even if no results
            report_dir = fm.resolve_path('reports')
            # Pass all_meeting_dates to ensure time period covers all analyzed files
            analyzer.generate_report(all_results, report_dir, grand_total_speakers, 
                                    all_meeting_dates=processed_meeting_dates, 
                                    all_meetings_metadata=all_meetings_metadata, 
                                    mask=args.mask,
                                    source_name=source_name,
                                    source_slug=source_slug)
            # stats['reported'] should be number of files processed in this phase
            stats['reported'] = len(target_ids)
    
    # Print status report
    print_status_report(stats, args, len(urls), processed_transcript_files, zero_results_files)
    
    # Cleanup before exit
    import gc
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except:
        pass
    gc.collect()

    end_time = datetime.datetime.now()
    elapsed = end_time - start_time
    hours, remainder = divmod(elapsed.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    print(f"\nProgram ran for {hours:02d}:{minutes:02d}  (Hours:Minutes).")

if __name__ == "__main__": main()
