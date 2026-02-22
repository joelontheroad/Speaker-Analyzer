# **********************************************************
# Public Meeting Speaker Analyzer
# file: utils/video_utils.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import datetime

class VideoUtils:
    @staticmethod
    def format_seconds(seconds):
        return str(datetime.timedelta(seconds=int(seconds or 0))).zfill(8)

    @staticmethod
    def get_swagit_link(base_url, seconds):
        if not base_url: return ""
        return f"{base_url.split('?')[0]}?ts={int(seconds)}"
