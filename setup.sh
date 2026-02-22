#!/bin/bash
# **********************************************************
# Public Meeting Speaker Analyzer
# file: setup.sh
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************

echo "[*] Initializing Environment..."
source .venv/bin/activate

echo "[*] Installing core dependencies..."
pip install --upgrade pip
pip install wheel setuptools packaging

# System Dependency Block
if ! command -v ffmpeg &> /dev/null; then
    echo "[!] ffmpeg is required but not installed."
    echo "    Please install it using: sudo apt-get install ffmpeg"
    exit 1
fi

# The package is 'whisperx'
echo "[*] Installing AI Stack..."
# Install Torch with CUDA support first, from PyTorch index
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install dependencies from requirements.txt
if [ -f "requirements.txt" ]; then
    echo "[*] Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
else
    echo "[!] requirements.txt not found, falling back to manual install..."
    pip install ctranslate2 requests beautifulsoup4 pyyaml yt-dlp chromadb numpy torchcodec==0.7.0
fi

# Finally, install WhisperX from git
echo "[*] Installing WhisperX..."
pip install git+https://github.com/m-bain/whisperx.git

echo "[+] Environment is synchronized."

# Configuration Setup
echo "[*] Checking configuration files..."

if [ ! -f "configs/defaults.yaml" ]; then
    echo "    - defaults.yaml not found. Creating from example..."
    cp configs/defaults.yaml.example configs/defaults.yaml
else
    echo "    - defaults.yaml already exists. Skipping copy."
fi

if [ ! -f "configs/prompts.yaml" ]; then
    echo "    - prompts.yaml not found. Creating from example..."
    cp configs/prompts.yaml.example configs/prompts.yaml
else
    echo "    - prompts.yaml already exists. Skipping copy."
fi

# Hardware Probing & Optimization
echo "[*] Probing Hardware for Optimization..."

# Default limits (Safe fallback)
CTX_LIMIT=4000
INPUT_LIMIT_IDENTITY=2500
INPUT_LIMIT_RELEVANCE=2500
INPUT_LIMIT_SENTIMENT=2000
INPUT_LIMIT_SUMMARY=2000

# check for nvidia-smi
if command -v nvidia-smi &> /dev/null; then
    echo "    - NVIDIA GPU detected."
    # Get total VRAM in MiB
    VRAM_MIB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n 1)
    echo "    - VRAM: ${VRAM_MIB} MiB"
    
    if [ "$VRAM_MIB" -ge 20000 ]; then
        # > 20GB VRAM (e.g. 3090/4090/A6000) -> 32k context safe
        echo "    - High-End GPU detected. Setting Max Context."
        CTX_LIMIT=32000
        INPUT_LIMIT_IDENTITY=15000
        INPUT_LIMIT_RELEVANCE=20000
        INPUT_LIMIT_SENTIMENT=25000
        INPUT_LIMIT_SUMMARY=25000
    elif [ "$VRAM_MIB" -ge 10000 ]; then
        # > 10GB VRAM (e.g. 3060/4070/A2000) -> 16k context likely safe (8B/12B models)
        echo "    - Mid-Range GPU detected (10GB+). Optimization enabled."
        CTX_LIMIT=16000
        INPUT_LIMIT_IDENTITY=10000
        INPUT_LIMIT_RELEVANCE=12000
        INPUT_LIMIT_SENTIMENT=12000
        INPUT_LIMIT_SUMMARY=12000
    else
        echo "    - Low VRAM (<10GB). Using standard limits."
    fi
else
    echo "    - No NVIDIA GPU detected. Using CPU defaults."
fi

# Update defaults.yaml using python for safety
python3 -c "
import yaml

config_path = 'configs/defaults.yaml'
try:
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f) or {}
    
    if 'ai_settings' not in config: config['ai_settings'] = {}
    if 'llm' not in config['ai_settings']: config['ai_settings']['llm'] = {}
    
    config['ai_settings']['llm']['context_window'] = $CTX_LIMIT
    config['ai_settings']['llm']['max_input_tokens'] = {
        'identity': $INPUT_LIMIT_IDENTITY,
        'relevance': $INPUT_LIMIT_RELEVANCE,
        'sentiment': $INPUT_LIMIT_SENTIMENT,
        'summary': $INPUT_LIMIT_SUMMARY
    }
    
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    print(f'    - Updated {config_path} with context limit: $CTX_LIMIT')
except Exception as e:
    print(f'    ! Failed to update config: {e}')
"

echo "[+] Setup Complete!"
