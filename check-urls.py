#!/usr/bin/env python3
# **********************************************************
# Public Meeting Speaker Analyzer
# file: check-urls.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import argparse
import sys
import os
import requests

from utils.logger import Logger
from utils.file_manager import FileManager
from utils.extractor import Extractor

def main():
    parser = argparse.ArgumentParser(description="Validate Meeting URLs for accessibility and connector support.")
    parser.add_argument("--url", help="Single URL to check")
    parser.add_argument("--batch", help="File containing a list of URLs to check (one per line)")
    parser.add_argument("--connector", help="Specific connector SLUG to require (e.g. Austin, Houston, YouTube)")
    parser.add_argument("--verbose", action="store_true", help="Show detailed errors")
    
    args = parser.parse_args()

    if not args.url and not args.batch:
        parser.print_help()
        sys.exit(1)

    log = Logger(verbose=args.verbose)
    fm = FileManager()
    # Device doesn't matter for metadata check
    ext = Extractor(log, fm, {'device': 'cpu'})

    # Validate connector if specified
    required_connector_cls = None
    if args.connector:
        from utils.discovery import get_available_connectors
        available = get_available_connectors(log)
        if args.connector not in available:
            log.error(f"Connector '{args.connector}' not found. Available: {', '.join(available.keys())}")
            sys.exit(1)
        required_connector_cls = available[args.connector]

    urls_to_check = []
    if args.url:
        urls_to_check.append(args.url.strip())
    
    if args.batch:
        if not os.path.exists(args.batch):
            log.error(f"Batch file not found: {args.batch}")
            sys.exit(1)
        with open(args.batch, 'r') as f:
            for line in f:
                url = line.strip()
                if url and not url.startswith('#'):
                    urls_to_check.append(url)

    if not urls_to_check:
        log.error("No URLs found to check.")
        sys.exit(1)

    total = len(urls_to_check)
    failed_urls = []
    
    print(f"Validating {total} URLs")
    
    spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

    for i, url in enumerate(urls_to_check, 1):
        # Header for current validation
        sys.stdout.write(f"\n[{i}/{total}] Validating: {url[:70]}...\n")
        
        # Initial status line with spinner
        spin_idx = 0
        sys.stdout.write(f" [{spinner[spin_idx]}] Initializing...")
        sys.stdout.flush()

        error_reason = None
        try:
            # 1. Connectivity/HTTP Check
            spin_idx = (spin_idx + 1) % len(spinner)
            sys.stdout.write(f"\r [{spinner[spin_idx]}] Checking HTTP Connectivity...")
            sys.stdout.flush()
            
            resp = requests.get(url, timeout=15)
            
            if resp.status_code != 200:
                error_reason = f"HTTP {resp.status_code}"
            else:
                # 2. Connector Check
                spin_idx = (spin_idx + 1) % len(spinner)
                sys.stdout.write(f"\r [{spinner[spin_idx]}] Identifying Connector Support...")
                sys.stdout.flush()
                
                if required_connector_cls:
                    if not required_connector_cls.can_handle(url):
                        error_reason = f"Not handled by requested connector '{args.connector}'"
                
                if not error_reason:
                    # 3. Metadata Check
                    spin_idx = (spin_idx + 1) % len(spinner)
                    sys.stdout.write(f"\r [{spinner[spin_idx]}] Verifying Metadata Extraction...")
                    sys.stdout.flush()
                    
                    meta = ext.get_meeting_metadata(url)
                    if meta.get('title') == "Unknown" or meta.get('media_url') is None:
                        error_reason = "Unsupported (No suitable connector found)"
                    elif "doesn't exist" in meta.get('title', '').lower():
                        error_reason = "Inaccessible (Swagit 404)"
        except requests.exceptions.RequestException as e:
            error_reason = f"Connection Error: {type(e).__name__}"
        except Exception as e:
            error_reason = f"Internal Error: {e}"

        # Final status line for this URL
        if error_reason:
            sys.stdout.write(f"\r ❌ {error_reason}\n")
            failed_urls.append((url, error_reason))
        else:
            sys.stdout.write(r" ✅ Valid" + "\n")
        sys.stdout.flush()

    print("\n" + "="*50)
    if not failed_urls:
        print("SUCCESS: All URLs validated successfully.")
        sys.exit(0)
    else:
        print(f"FAILURE: {len(failed_urls)} URL(s) failed validation:")
        for url, reason in failed_urls:
            print(f"  - {url}: {reason}")
        sys.exit(1)

if __name__ == "__main__":
    main()
