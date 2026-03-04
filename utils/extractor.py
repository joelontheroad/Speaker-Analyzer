# **********************************************************
# Public Meeting Speaker Analyzer
# file: utils/extractor.py
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************
import os, subprocess, re, sys, shutil, json, importlib, inspect

class Extractor:
    def __init__(self, logger, file_manager, hw_profile):
        self.log, self.fm, self.hw = logger, file_manager, hw_profile
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0
        self.staging_dir = "tmp_processing"
        os.makedirs(self.staging_dir, exist_ok=True)
        
        self.connectors = []
        self._load_connectors()

    def _get_spinner(self):
        char = self.spinner_chars[self.spinner_idx % len(self.spinner_chars)]
        self.spinner_idx += 1
        return char

    def _spinner_start(self, message):
        """Start a spinner animation"""
        sys.stdout.write(f"[{self._get_spinner()}] {message}")
        sys.stdout.flush()

    def _spinner_update(self, message):
        """Update spinner animation"""
        sys.stdout.write(f"\r[{self._get_spinner()}] {message}")
        sys.stdout.flush()

    def _spinner_done(self):
        """Clear spinner line"""
        print()

    def _load_connectors(self):
        from utils.discovery import get_available_connectors
        available = get_available_connectors(self.log)
        
        for slug, cls in available.items():
            try:
                self.connectors.append(cls(self.log, self.fm))
                if hasattr(self.log, 'debug'):
                    self.log.debug(f"Loaded connector: {cls.__name__} ({slug})")
            except Exception as e:
                self.log.error(f"Failed to instantiate connector {slug}: {e}")

    def get_meeting_metadata(self, url):
        selected_connector = None
        for connector in self.connectors:
            try:
                if connector.can_handle(url):
                    selected_connector = connector
                    break
            except Exception as e:
                self.log.warning(f"Error checking can_handle for {connector.__class__.__name__}: {e}")
        
        # Default to Youtube (Generic) if no specific match found
        if not selected_connector:
            fallback = next((c for c in self.connectors if 'youtube' in c.__class__.__name__.lower()), None)
            if fallback:
                selected_connector = fallback
            elif self.connectors:
                selected_connector = self.connectors[-1]
            else:
                 self.log.error("No connectors available.")
                 return None
            
        try:
            meta = selected_connector.get_metadata(url)
        except Exception as e:
            self.log.error(f"Metadata extraction crashed in {selected_connector.__class__.__name__}: {e}")
            return None
            
        # Validation
        if not meta or not isinstance(meta, dict):
             self.log.error(f"Connector {selected_connector.__class__.__name__} returned invalid or no metadata.")
             return None
             
        # Check required fields
        required_keys = ['title', 'date', 'media_url']
        missing_keys = [k for k in required_keys if k not in meta or not meta[k] or str(meta[k]).lower() in ['unknown', 'unknown date']]
        if missing_keys:
             self.log.error(f"CRITICAL ERROR: Connector {selected_connector.__class__.__name__} missing required metadata: {missing_keys}")
             self.log.error("This meeting cannot be processed without a valid title and date.")
             return None

        # Type checking and normalization
        try:
             # Ensure offset is an int
             if 'offset' in meta:
                 meta['offset'] = int(meta['offset'])
             else:
                 meta['offset'] = self.fm.get_ai_setting('analysis', 'default_start_offset') or 0
        except (ValueError, TypeError):
             meta['offset'] = 0
             
        # String normalization
        meta['title'] = str(meta['title']).strip()
        meta['date'] = str(meta['date']).strip()
        meta['media_url'] = str(meta['media_url']).strip()

        return meta

    def run_acquisition(self, manifest, force=False):
        vid_id = manifest['video_id']
        url = manifest['source_url']
        audio_only = manifest.get('audio_only', True)
        
        # Get metadata using the source URL
        meta = self.get_meeting_metadata(url)
        
        if not meta:
            self.log.error(f"Critical: Could not acquire metadata for {vid_id}. Skipping acquisition.")
            return None, None

        # Override media_url in manifest if found in meta
        download_url = meta.get('media_url', url)
        
        # Use duration from metadata if provided, otherwise fallback to default
        duration = meta.get('duration')
        if not duration or duration <= 0:
            duration = self.fm.get_ai_setting('analysis', 'default_duration') or 1800
        
        final_path = os.path.join(self.fm.resolve_path('media'), f"{vid_id}_audio.mp3")
        meta_path = os.path.join(self.fm.resolve_path('summaries'), f"{vid_id}_metadata.json")
        staging_path = os.path.join(self.staging_dir, f"{vid_id}_audio.mp3")

        # Atomic metadata write
        # Merge manifest with meta, but keep manifest ID
        full_meta = {**manifest, **meta}
        full_meta['media_url'] = download_url # Ensure we save what we used
        full_meta['duration'] = duration     # Ensure we save what we used
        
        with open(meta_path, 'w') as f:
            json.dump(full_meta, f, indent=4)

        if os.path.exists(final_path) and not force:
            self.log.info(f"File {vid_id} already exists in vault. Skipping.")
            return final_path, full_meta

        start, end = meta.get('offset', 0), meta.get('offset', 0) + duration
        
        cmd = ['yt-dlp', '--newline']
        if force:
            cmd.append('--force-overwrites')
        else:
            cmd.append('--no-overwrites')
        if audio_only:
            cmd.extend(['-x', '--audio-format', 'mp3'])
        
        # For COA/Swagit, we might be downloading from a direct MP4 or m3u8.
        # Now that we prioritize m3u8, download-sections should work efficiently.
        output_template = os.path.join(self.staging_dir, f"{vid_id}_audio.%(ext)s")
        # Ensure start/end are valid numbers or strings before f-string
        s_val = str(start) if start is not None else "0"
        e_val = str(end) if end is not None else "1800"
        
        if not download_url:
            self.log.error(f"No download URL found for {vid_id}")
            return None, None
            
        cmd.extend(['--download-sections', f"*{s_val}-{e_val}", '--output', output_template, download_url])
        
        # cmd.extend(['--output', staging_path, download_url])
        # cmd.extend(['--postprocessor-args', f"ffmpeg:-t {duration}"])

        self.log.info(f"Downloading {vid_id} from {download_url} ({start}-{end})...")
        if self.log.verbose:
            print(f"DEBUG CMD: {' '.join(cmd)}")
            
        # bufsize=1 enables line buffering for real-time output
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        output_lines = []
        for line in proc.stdout:
            output_lines.append(line)
            if '%' in line:
                # yt-dlp output format example: [download]  50.5% of 10.00MiB at 1.00MiB/s ETA 00:05
                # or [download] 0.305091%
                match = re.search(r'(\d+(?:\.\d+)?)%', line)
                if match:
                    try:
                        raw_val = float(match.group(1))
                        # The user noted that some percentages might be given as actual fractions (e.g. 0.31 instead of 31%)
                        # Let yt-dlp output be parsed as-is, round it. 
                        # Wait, if yt-dlp says "0.305091%", it means less than 1%.
                        pct = round(raw_val)
                        sys.stdout.write(f"\r[{self._get_spinner()}] Downloading {vid_id}: {pct}%")
                        sys.stdout.flush()
                    except ValueError:
                        pass
            elif 'Frag' in line or 'frag' in line:
                # m3u8 playlists output format: [download] Destination: ... [download]  15.0% (15/100)
                # or [download] frag 5/120
                match = re.search(r'(?:frag|Frag)\s+(\d+/\d+)', line)
                if match:
                    sys.stdout.write(f"\r[{self._get_spinner()}] Downloading {vid_id} (Chunk {match.group(1)})...")
                    sys.stdout.flush()
            elif 'size=' in line or 'time=' in line:
                # ffmpeg output format: size=     256kB time=00:00:10.00
                match = re.search(r'time=(\d+:\d+:\d+\.\d+)', line)
                if match:
                    sys.stdout.write(f"\r[{self._get_spinner()}] Downloading {vid_id} (Time {match.group(1)})...")
                    sys.stdout.flush()
                else:
                    match_size = re.search(r'size=\s*(\d+[a-zA-Z]+)', line)
                    if match_size:
                        sys.stdout.write(f"\r[{self._get_spinner()}] Downloading {vid_id} (Size {match_size.group(1)})...")
                        sys.stdout.flush()
        
        proc.wait()
        self._spinner_done()

        if proc.returncode != 0:
            self.log.error(f"yt-dlp failed with return code {proc.returncode}")
            self.log.error("Output:\n" + "".join(output_lines))
        
        # Determine success
        # yt-dlp might have produced .mp3 directly or kept original ext if conversion failed
        # We look for vid_id_audio.mp3 in staging
        
        found_path = None
        # Check explicit mp3 first
        if os.path.exists(staging_path):
             found_path = staging_path
        else:
             # Check for any file starting with vid_id_audio
             prefix = f"{vid_id}_audio"
             for f in os.listdir(self.staging_dir):
                 if f.startswith(prefix) and not f.endswith('.part'):
                     # Found a candidate (e.g. .m4a, .webm)
                     # If it's not mp3, we might want to convert it?
                     # But Extractor expects mp3 for transcription (WhisperX handles most, but we standardized on mp3)
                     # For now, just return it and let valid path propagate, assuming WhisperX can handle it or we rename?
                     # Actually, if we requested mp3, it should be mp3.
                     # If it's seemingly successful but not mp3, maybe move it?
                     found_path = os.path.join(self.staging_dir, f)
                     break

        if proc.returncode == 0 and found_path:
            # If not mp3, we should probably warn, but WhisperX handles other formats too.
            # But the rest of the pipeline expects _audio.mp3 naming convention in vault?
            # Yes, run_transcription looks for _audio.mp3.
            
            target_ext = os.path.splitext(found_path)[1]
            if target_ext != '.mp3':
                 self.log.warning(f"Downloaded file is {target_ext}, expected .mp3. Renaming/Converting?")
                 # If ffmpeg is present, yt-dlp should have converted.
                 # If we just rename, it might be wrong container, but WhisperX calls ffmpeg anyway.
                 # Let's enforce the target name in vault.
            
            shutil.move(found_path, final_path)
            # Cleanup potential sidecar files from yt-dlp if any?
            return final_path, full_meta
        
        self.log.error(f"Acquisition failed for {vid_id}")
        return None, None

    def run_transcription(self, video_id, force=False, translate_to_english=False):
        import whisperx
        import torch
        import gc
        import warnings
        
        # Suppress warnings for cleaner output
        warnings.filterwarnings('ignore', category=UserWarning)
        warnings.filterwarnings('ignore', category=FutureWarning)
        
        out_file = os.path.join(self.fm.resolve_path('transcripts'), f"{video_id}_transcript.json")
        if os.path.exists(out_file) and not force: return out_file
        
        media_path = os.path.join(self.fm.resolve_path('media'), f"{video_id}_audio.mp3")
        if not os.path.exists(media_path):
            self.log.error(f"Missing media for transcription: {media_path}")
            return None

        self.log.info(f"Phase 2: Transcribing {video_id} with WhisperX...")
        
        device = self.hw['device']
        # Use compute_type float16 if cuda, else int8
        compute_type = "float16" if device == "cuda" else "int8"
        
        try:
            model = whisperx.load_model("small", device, compute_type=compute_type)
            audio = whisperx.load_audio(media_path)
            
            # Transcription with spinner
            self._spinner_start(f"Transcribing {video_id}_audio.mp3...")
            batch_size = self.fm.config.get('ai_settings', {}).get('transcription', {}).get('batch_size', 8)
            
            transcribe_args = {"batch_size": batch_size}
            if translate_to_english:
                transcribe_args["task"] = "translate"
                
            result = model.transcribe(audio, **transcribe_args)
            self._spinner_done()
            
            # Free GPU memory after transcription
            del model
            gc.collect()
            if device == "cuda":
                torch.cuda.empty_cache()
            
            # Alignment with spinner
            self._spinner_start(f"Aligning {video_id}_transcript.json...")
            model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
            result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
            self._spinner_done()
            
            # Free GPU memory after alignment
            del model_a, metadata
            gc.collect()
            if device == "cuda":
                torch.cuda.empty_cache()

            # Diarization (Speaker Identification) with spinner
            try:
                # Get HF token from config
                hf_token = self.fm.get_network_setting('hf_token')
                if not hf_token or hf_token.strip() == "":
                    self.log.warning("No HF_TOKEN configured in defaults.yaml. Skipping diarization.")
                    self.log.warning("Speaker identification will not work. All speakers will be 'Unknown'.")
                else:
                    from whisperx.diarize import DiarizationPipeline
                    # Get diarization model name from config
                    diarization_model_name = self.fm.config.get('ai_settings', {}).get('diarization', {}).get('model', 'pyannote/speaker-diarization-3.1')
                    self._spinner_start(f"Identifying speakers in {video_id}_audio.mp3...")
                    diarize_model = DiarizationPipeline(model_name=diarization_model_name, token=hf_token, device=device)
                    diarize_segments = diarize_model(audio)
                    result = whisperx.assign_word_speakers(diarize_segments, result)
                    self._spinner_done()
                    
                    # Free GPU memory after diarization
                    del diarize_model, diarize_segments
                    gc.collect()
                    if device == "cuda":
                        torch.cuda.empty_cache()
            except Exception as e:
                self.log.error(f"Diarization failed (Speaker analysis will be limited). Ensure HF_TOKEN is set if needed: {e}")

            with open(out_file, 'w') as f:
                json.dump(result, f, indent=4)
                
            return out_file
        except Exception as e:
            self.log.error(f"Transcription failed: {e}")
            return None
