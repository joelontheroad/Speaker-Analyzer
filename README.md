## Overview
Welcome to the Public Meeting Speaker Analyzer utility. A configurable, private, AI-powered tool for transcribing the video of public meetings; summarizing what people said; and reporting on sentiment. It's private in that it's designed to run on a local machine with a GPU, whether that's your desktop, a laptop, or a server on your local network. Journalists, researchers, and others in civil society will find this tool useful. 

You tell the program what to analyze using a natural language prompt and then help the AI refine it's analysis by also providing keywords. You can also define sentiment categories to the AI determine sentiment of each speaker on the topic in which you're interested. 

Setup is potentially easy as it consists of running a single command, `./setup.sh`. It will install all files and dependencies.

Inspired by security and privacy principals in mind, you can mask the names of speakers so that you can distribute your findings, retaining their privacy. Be sure to check local laws before distributing reports.

## Features
-   **Links to Video**: All reports include links to the exact place where someone said something cited in a report so you can quickly jump to it and hear exactly what a person said. 
-   **Modular Architecture**: Includes connectors for City of Austin, City of Houston, and YouTube. Other connectors to different video sources can be created by anyone so you can perform analysis on any public meeting database that doesn't restrict downloads.
-   **Privacy Feature**: Optional masking of speaker names (--mask cli flag) so that you can share reports while maintaining the privacy of the speakers. 
-   **Local AI Analysis**: Connects to any local LLM provider that use adheres to the openAI API specification (e.g., LM Studio) for all AI anlaysis. Use whatever AI model runs on your GPU. All your data stays in your network; you're not sharing any information with a SaaS service.
-   **Flexible CLI**: Run phases (Download, Transcribe, Report) individually or all at once. Download the media once, report again and again even with different prompts to extract the most knowledge you can.
-   **Ad-hoc Questions**: In addition to the standard reports, you can ask any question you like of the knowledge base you've downloaded it, regardless of what was prompted in the reports.  Allows you to ask questions once you gain insights from the reports.  

## How It Works

The main program, speaker-analyzer.py, runs in three phases:
Phase 1: download media
Phase 2: transcribe audio into text with time code
Phase 3: Run reports

This means you have a knowledge base of of everything downloaded. In addition to running the reports, helper programs have been included to:
* Count the number of speakers making the similar arguments (argument-analyzer.py)
* Format the knowledge base so that questions can be asked of it (knowledge-indexer.py)
* Ask additional questions of the knowledge base (ask-this.py)


## Suggested Hardware and Software Requirements
The program has been developed on the following hardware/software configuration. It should run on others.
-   **OS**: Linux (Pop!_OS / Ubuntu recommended with GPU support)
-   **Hardware**: GPU (nvidia RTX A2000 with 12GB was in the dev machine) for transcribing and AI analysis.
-   **Software**:
    -   Python 3.10+
    -   LM Studio (running locally; this and the hard drives are the key to this program being "Local AI")
    -   FFmpeg
-   **Hugging Face**: A Hugging Face token (`HF_TOKEN`) is required for `pyannote` speaker diarization.

## Getting Started

### 1. Prerequisites & Model Access
WhisperX uses **Pyannote** for speaker diarization (identifying who is speaking). These models are "gated" on Hugging Face, meaning you must manually accept their terms of use before the program can download them.

1.  **Create an Account**: Sign up at [huggingface.co](https://huggingface.co/join).
2.  **Accept Model Terms**: Use these links to visit the model pages. While logged in, click the **"Agree and access repository"** button for both:
    *   [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
    *   [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
3.  **Generate a Token**: 
    *   Go to **Settings** > **Access Tokens** ([hf.co/settings/tokens](https://huggingface.co/settings/tokens)).
    *   Click **New token**.
    *   Name it (e.g., "Speaker-Analyzer") and set the type to **Read**.
    *   Copy the token; you'll need it for your configuration.

#### Does it contact Hugghing Face every run?
Yes. Because these models are gated, the program needs to provide your token to Hugging Face at the start of every transcription phase (Phase 2) to verify you still have permission to use the model. While the heavy model files (several GBs) are cached locally after the first run, the program performs a brief "handshake" with Hugging Face for each video processed.

### 2. Installation
Clone the repository and run the setup script. This will create a virtual environment and install the necessary AI stack (Torch, WhisperX, etc.).

```bash
git clone https://github.com/your-repo/speaker-analyzer
cd speaker-analyzer
./setup.sh
```

### 3. Initial Configuration
The setup script will create your local configuration files from templates. You need to provide your API keys and server URLs:

1.  Open `configs/defaults.yaml`.
2.  **Hugging Face**: Paste your token into the `hf_token` field.
3.  **LLM Support**: Update `llm_api_url` to point to your local LLM provider (e.g., `http://127.0.0.1:1234` for LM Studio).

### 4. Running a Test
Once configured, you can verify everything is working by checking a single URL:
```bash
python speaker-analyzer.py --url "https://austintx.swagit.com/play/304099/0/" --all
```

## Configuration
-   **`configs/defaults.yaml`**: Set paths, model sizes, and network settings. 
-   **`configs/prompts.yaml`**: Define the Topic, Keywords, and Sentiment for the AI analysis.

## Usage
Run the main script:
```bash
python speaker-analyzer.py [OPTIONS]
```

#### How to run the program ####
The program runs in three distinct phases.  All Phases can be run one after the other (default), or one at a time. The phases are:
- Phase 1: Download media files.  The default is to only download the audio where it's available distinct from the video so as to save time and space. The user can tell the program to download the video instead, which always contains the audio.
- Phase 2: Extract the text of the audio in the media files that are downloaded and save in text files. These text files contain the date and beginnning time of the video and time from the beginning when each speaker begins speaking.
- Phase 3: Analyze the existing text files. The program then discovers all the speakers and what they they've said about the topic the user has defined.  The program creates two summary reports:  1) A report on the speaker and their sentiment for each meeting and 2) It summarizes all the speakers and how many meetings at which they spoke. 

The user can run any of these phases individually if there are files from the previous phase.  For example, the user can have the program download media files and stop in order to makes sure all files downloaded correctly before going onto a time intensive analysis phase. 

Here are examples of all the ways the user can run the program:

Run the program from Phase 1 to Phase 3 without stopping.
Run Phase 2 only and then stop. Doing so assumes media files exist from Phase 1.
Run Phase 3 only and then stop.  Doing so assumes text extraction files exist from Phase 2, which in turn assumes media files exist from Phase 1.

These are the only valid ways to run the program.  The program will provide you an error message if you run these invalid ways:
- Running Phase 2 without running Phase 1. Reason it's invalid: there are no media files from which to extract the audio and analyze it.
- Running Phase 3 without running Phase 2. Reason it's invalid: there are no text extraction files from Phase 2 to analyze.

#### Looking for different sentiment ####
By changing what the program is looking for via the configs/prompts.yaml file, you can generate a new report on a different topic as long there were speakers who spoke on that topic in the media.  This is useful for analyzing the Public Comment section of City Council Meetings where anyone can bring any topic to the attention of the government.  

#### Telling the program which video to analyze ####
The user can give URL's to the program to analyze in two ways:
1) On the command line. This is good for doing one or two videos you'd like to quickly analyze.
2) In a text file, one video URL at a time.  This is the preferred method as it allows a way to run a batch of videos at one time. This is especially useful for having the program run overnight.  Hash tags, "#", are viewed as comments in the text file and are ignored. You can use these to keep your URLs organized.

When analyzing and reporting in Phase 3, the user can instruct the program to mask the user names so they are not identifiable. The program will give a unique number to each speaker; in other words, the speaker will not be identifiable, but will still be unique.  For example, John Doe can appear as Speaker# AED343D". This is accomplished with a one way hash. Use this feature when making the results of the analysis public in order to retain the privacy of the speakers.
### Common Commands
-   **Process a single URL (End-to-End):**
    ```bash
    python speaker-analyzer.py --url "https://austintexas.gov/watch/video/..." --all
    ```
-   **Process a batch of URLs:**
    ```bash
    python speaker-analyzer.py --batch my_videos.txt --all
    ```
-   **Only Transcribe (if media already downloaded):**
    ```bash
    python speaker-analyzer.py --transcribe
    ```
-   **Generate Reports (if transcribed):**
    ```bash
    python speaker-analyzer.py --report --mask
    ```

### CLI Options
-   `--url URL`: Download the media in the URL.
-   `--batch FILE`: Download all media in a text file.
-   `--connector SLUG`: Specify which city or source connector to use (e.g., Austin, Houston). **Optional** when `--url` is provided, as the program will automatically detect the correct city from the URL. Acts as an override or for non-URL phases (like `--report`).
-   `--list-connectors`: List all available connectors/cities and exit.
-   `--all`: Run all phases (Download -> Transcribe -> Report).
-   `--transcribe`: Run transcription phase only.
-   `--report`: Generate final report only.
-   `--mask`: Mask speaker names for privacy.
-   `--english`: Force Whisper to translate non-English audio into English during transcription.
-   `--video`: Force video download (default is audio-only).
-   `--force`: Force overwrite existing files.
-   `--verbose`: Enable verbose logging.

#### Partial Reports (Report Subset Flags) ####
These flags are used with `--report` to run the analysis on a subset of your transcripts, ordered
chronologically from oldest to newest. They are mutually exclusive — use only one at a time.

-   `--first N`: Report on the **first N meetings** only (oldest N).
-   `--last N`: Report on the **last N meetings** only (most recent N).
-   `--between N-Y` or `--between N,Y`: Report on meetings **N through Y inclusive** (1-indexed).

**Examples:**
```bash
# Quick check — report on just the 3 most recent meetings
python speaker-analyzer.py --report --last 3

# Report on only the very first meeting in your dataset
python speaker-analyzer.py --report --first 1

# Report on meetings 4 through 8 in chronological order
python speaker-analyzer.py --report --between 4-8
```

## Additional Programs

This repository includes several standalone utility programs that extend the analysis capabilities of the main pipeline:

### 1. `argument-analyzer.py`
The main program.  This program reads through all fully-transcribed meetings and uses the LLM to extract every raw claim made by the speakers. It then semantically clusters these identical or highly similar claims into organized "canonical" arguments, showing exactly how many people argued for the same point regardless of how they phrased it.

**CLI Options:**
-   `--mask`: Mask speaker names in LLM prompts to ensure their identities remain private during extraction and analysis.

**Usage:** Runs automatically on the `transcripts/` directory. Outputs both Markdown and HTML reports to the workspace `reports/` folder.

### 2. `knowledge-indexer.py`
This program acts as the ingest engine for the Retrieval-Augmented Generation (RAG) system. It chunks all available transcript text into semantic blocks while preserving the speaker metadata, timestamps, and video URLs, and then creates vector embeddings to store in a local ChromaDB database.

**Usage:** Run this program whenever you have new transcripts that you want to be able to search against. No flags are required.

### 3. `ask-this.py`
This program allows you to ask natural language questions against the entire recorded history of city council meetings using the RAG database built by the indexer. It will search for relevant context and have the LLM form an answer containing inline deep-links directly back to the exact timestamp in the source video where the speaker made the statement.

**CLI Options:**
-   `-q`, `--query STRING`: Ask a single quoted question directly in the terminal (e.g., `-q "What did they say about zoning?"`).
-   `-f`, `--file PATH`: Pass a text file containing one or more questions. The program will parse the file line-by-line and answer every question sequentially.
-   `--separate`: By default, batch file queries are combined into a single running Markdown/HTML report document. Use this flag to force the program to output each question's answer into its own isolated file instead.
-   `--mask`: Mask speaker names in the context provided to the LLM and in all generated source citations for privacy.
-   `--sentiment CLASS`: Pre-filter the database search to only include speakers with a specific sentiment class (e.g., `--sentiment "Pro-Israel"`). Highly recommended for side-specific queries to eliminate cross-contamination from the other side.

### 4. `check-urls.py`
A validation utility used to "dry-run" your input URLs before starting a long transcription process. It verifies that URLs are accessible, confirms that a compatible connector is available, and ensures that metadata (like titles and media streams) can be successfully extracted.

**CLI Options:**
-   `--url URL`: Validate a single URL.
-   `--batch FILE`: Validate a list of URLs from a text file (one per line).
-   `--connector SLUG`: Manually specify which connector should handle the URL (e.g., `Austin`, `Houston`, `YouTube`).
-   `--verbose`: Show detailed error messages for any failures.

**Usage:** Helps prevent wasted time by identifying broken links or unsupported sources before you run the main `speaker-analyzer.py` pipeline.


## Directory Structure
-   `workspaces/`: Root directory for all workspace-specific data.
    -   `{Slug}/`: Individual workspace (e.g., `Austin`, `YouTube`).
        -   `media/`: Downloaded audio/video files.
        -   `transcripts/`: JSON transcripts with speaker data.
        -   `summaries/`: Speaker manifests and metadata.
        -   `reports/`: Final Markdown and HTML reports.
        -   `db/`: Local ChromaDB vector database.
-   `configs/`: Global configuration files.
-   `logs/`: Application logs.

### The Program's Approach to Privacy and Security ###
This program was designed as a "Private AI". It assumes media files are downloaded from the public internet to a private network behind an industry standard firewall and that all analysis are done on GPU's located in the network behind that firewall. The intent is that all files stay within this private network. The program does not communicate with the Internt except when downloading files.  In this way, all analysis and reporting is private.  The program doesn not enforce this requirement, so it's assumed that the user will use it that way. By using an encrypted hard drive for the media files, you may actually be able to pass security certification, but there's no guarantee. If this an issue, consult a compliance professional. This program connects to the Internt to: 1) download media files, and 2) get validation from Hugging Face to use their models at run time.  That's it. Future versions will eliminate the need for getting validation every time from Hugging Face.  If you already have have a media database, you can point to it via defaults.yaml and not have to go out to the Internet.

