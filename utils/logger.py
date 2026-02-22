# **********************************************************
# Public Meeting Speaker Analyzer
# file: utils/logger.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import sys, os, datetime
class Logger:
    def __init__(self, verbose=False, log_dir=None): 
        self.verbose = verbose
        self.log_file = None
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = os.path.join(log_dir, f"analyzer_{timestamp}.log")
            try:
                with open(self.log_file, 'a') as f:
                    f.write(f"--- Log Started: {timestamp} ---\n")
            except Exception as e:
                print(f"[!] Failed to init log file: {e}", file=sys.stderr)

    def _log(self, prefix, m, dest=sys.stdout):
        msg = f"{prefix} {m}"
        print(msg, file=dest)
        if self.log_file:
            try:
                with open(self.log_file, 'a') as f:
                    f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n")
            except: pass

    def info(self, m): 
        if self.verbose: 
            self._log("[*]", m)
        elif self.log_file:
            # Log to file even if not verbose
            try:
                with open(self.log_file, 'a') as f:
                    f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [*] {m}\n")
            except: pass
    def success(self, m): self._log("[+]", m)
    def warning(self, m): self._log("[-]", m)
    def error(self, m): self._log("[!]", m, dest=sys.stderr)
