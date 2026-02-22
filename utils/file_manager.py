# **********************************************************
# Public Meeting Speaker Analyzer
# file: utils/file_manager.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import yaml, os
class FileManager:
    def __init__(self, config_path="configs/defaults.yaml", connector_slug=None):
        self.config_path = config_path
        with open(self.config_path, 'r') as f: self.config = yaml.safe_load(f)
        self.connector_slug = connector_slug or self.config.get('default_connector', 'Generic')

    def resolve_path(self, key):
        paths_config = self.config.get('paths', {})
        p = paths_config.get(key)
        
        # If it's a workspace-specific subfolder (media, transcripts, etc.)
        workspace_keys = ['media', 'transcripts', 'summaries', 'reports', 'db']
        if key in workspace_keys:
            root = paths_config.get('workspace_root')
            if not root:
                 # Fallback to local work dir if root not defined
                 root = "./workspaces"
            
            p = os.path.join(root, self.connector_slug, key)
            
        if p: os.makedirs(p, exist_ok=True)
        return p

    def get_ai_setting(self, cat, key): return self.config.get('ai_settings', {}).get(cat, {}).get(key)
    def get_network_setting(self, key): return self.config.get('network', {}).get(key)
