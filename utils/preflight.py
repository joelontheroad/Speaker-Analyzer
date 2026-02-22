# **********************************************************
# Public Meeting Speaker Analyzer
# file: utils/preflight.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import sys, requests

class Preflight:
    def __init__(self, logger, file_manager=None): 
        self.log = logger
        self.fm = file_manager

    def run_checks(self):
        # 1. Check Virtual Env
        if not (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)):
             self.log.error("Virtual environment not activated. Run: source .venv/bin/activate")
             return False
        
        # 2. Check LLM Connectivity - soft check here, strict check when calling check_llm_availability(enforce=True)
        # We don't enforce it by default in run_checks because some phases (download) don't need it.
        # But let's log a warning if it's down.
        if not self.check_llm():
            self.log.warning("LLM appears to be offline. Analysis/Reporting phases will fail.")
            
        return True

    def check_llm_availability(self, enforce=True):
        """Public method to check LLM availability, optionally enforcing it."""
        is_online = self.check_llm()
        if not is_online and enforce:
            self.log.error("Critical: LLM is offline. This phase requires LLM connectivity.")
            return False
        return is_online

    def check_llm(self):
        if not self.fm: return True # Skip if no FM provided (shouldn't happen in main)
        
        api_url = self.fm.get_network_setting('llm_api_url') or "http://127.0.0.1:1234"
        # Ensure we check the base URL or models endpoint
        check_url = f"{api_url.rstrip('/')}/v1/models"
        
        try:
            self.log.info(f"Checking LLM connectivity at {check_url}...")
            resp = requests.get(check_url, timeout=2)
            if resp.status_code == 200:
                self.log.info("LLM is Online.")
                return True
            else:
                self.log.error(f"LLM reports status {resp.status_code}. Is it running?")
        except Exception as e:
            self.log.error(f"LLM is OFFLINE or unreachable: {e}")
            self.log.error("Please start LM Studio (or compatible server) on port 1234.")
            
        return False

    def get_hw(self):
        try: import torch; return {"device": "cuda" if torch.cuda.is_available() else "cpu"}
        except: return {"device": "cpu"}
