#!/bin/bash
# **********************************************************
# Public Meeting Speaker Analyzer
# file: run-all.sh
# Version: 0.1.0
#
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Joel Greenberg
# **********************************************************

# Activate the virtual environment automatically!
source .venv/bin/activate

# Define colors
GREEN='\e[32m'
RED='\e[31m'
NC='\e[0m' # No Color (Reset)

# setup elapsed time
# Capture the start time
start_time=$SECONDS

 
# =============  Houston ================================
# 1. Run reporting only Houston,  the standard unmasked version
echo ""
echo -e "${GREEN}Houston only reporting (and transcribing if necessary) starting at $(date +'%I:%M %P')${NC}"
echo ""
echo -e "${GREEN}Generating standard report for Houston...${NC}"

./speaker-analyzer.py --transcribe --report  --connector Houston


echo -e "${GREEN}Houston report Generation Complete!${NC}"
echo ""

# 2. Run ONLY the REPORT phase (--report) with masking enabled (--mask)
# This is very fast because the LLM summaries are already cached!
echo -e "${GREEN}Generating masked report for Houston...${NC}"

python3 speaker-analyzer.py --report --mask --connector Houston

echo -e "${GREEN}Houston masked eport Generation Complete!${NC}"
echo ""


# 2.5 Run Argument Summarizer

echo -e "${GREEN}Generating argument summarizer report for Houston...${NC}"

python3 argument-analyzer.py --connector Houston

echo -e "${GREEN}Houston argument analyzer eneration Complete!${NC}"
echo ""


#3. Get Knowledge base ready for questions
echo -e "${GREEN}Running knowledge base indexer for Houston- only needs to be run per data pull.${NC}"

# python3 knowledge-indexer.py --connector Houston

echo -e "${GREEN}Houston Knowledge base indexed!${NC}"
echo ""

# echo -e "${GREEN}Body of Knowledge of Houston now being asked questions${NC}"
# python3 ask-this.py --file questions-to-ask.txt --connector Houston

# echo -e "${GREEN}All questions answered!${NC}"
echo ""


# =============  Exit ================================

# Calculate total seconds
elapsed=$(( SECONDS - start_time ))

# Break it down into minutes and remaining seconds
minutes=$(( elapsed / 60 ))
seconds=$(( elapsed % 60 ))

echo "Total Elapsed Time: ${minutes}m ${seconds}s"


echo -e "${GREEN}Done batch processing.${NC}"
echo "Exiting batch script at $(date +'%I:%M %P')"
