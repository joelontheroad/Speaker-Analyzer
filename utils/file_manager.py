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
        self.config = self.load_yaml(self.config_path)
        self.connector_slug = connector_slug or self.config.get('default_connector', 'Generic')

    @staticmethod
    def load_yaml(file_path):
        import sys
        try:
            with open(file_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            print(f"\n[ERROR] Malformed YAML in {file_path}")
            if hasattr(exc, 'problem_mark'):
                mark = exc.problem_mark
                print(f"Syntax error at line {mark.line + 1}, column {mark.column + 1}:")
                if getattr(exc, 'problem', None) is not None:
                    print(f"Problem: {exc.problem}")
                if getattr(exc, 'context', None) is not None:
                    print(f"Context: {exc.context}")
                
                try:
                    with open(file_path, 'r') as f:
                        lines = f.readlines()
                        if mark.line < len(lines):
                            line_text = lines[mark.line].rstrip('\n')
                            print(f"\n{mark.line + 1} | {line_text}")
                            prefix_len = len(str(mark.line + 1)) + 3 + mark.column
                            print(" " * prefix_len + "^")
                            print(" " * prefix_len + "|-- Formatting error near here\n")
                except Exception:
                    pass
            else:
                print(f"Error details: {exc}")
            
            print("Please fix the formatting in the file and try again.")
            sys.exit(1)
        except Exception as e:
            print(f"\n[ERROR] Could not read YAML file {file_path}: {e}")
            return {}

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
