# **********************************************************
# Public Meeting Speaker Analyzer
# file: utils/parser.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import os, re

class Parser:
    def __init__(self, logger, file_manager):
        self.log = logger
        self.fm = file_manager
        self.skip_ids = self._load_skip_ids()

    def _load_skip_ids(self):
        skip_path = self.fm.resolve_path('skip_ids')
        if skip_path and os.path.exists(skip_path):
            with open(skip_path, 'r') as f:
                return [line.strip() for line in f if line.strip() and not line.startswith('#')]
        return []

    def extract_speakers(self, text):
        speaker_pattern = r"([A-Z\s\-]+)\s\((\d{2}:\d{2}:\d{2})\):"
        segments = re.split(speaker_pattern, text)
        parsed = []
        for i in range(1, len(segments), 3):
            name = segments[i].strip()
            if name in self.skip_ids: continue
            parsed.append({"speaker": name, "time": segments[i+1], "text": segments[i+2].strip()})
        return parsed
