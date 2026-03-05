# Open Meeting Speaker Analyzer

## Overview of Speaker Analyzer
Welcome to the Public Meeting Speaker Analyzer utility. A configurable, private, AI-powered tool for transcribing the video of public meetings; summarizing what people said; and reporting on sentiment. It's private in that it's designed to run on a local machine with a GPU, whether that's your desktop, a laptop, or a server on your local network. Journalists, researchers, and others in civil society will find this tool useful. 

You tell the program what to analyze using a natural language prompt and then help the AI refine it's analysis by also providing keywords. You can also define sentiment categories to the AI determine sentiment of each speaker on the topic in which you're interested. 

Setup is potentially easy as it consists of running a single command, `./setup.sh`. It will install all files and dependencies.

To maintain privacy,you can mask the names of speakers so that you can distribute your findings, retaining their privacy. This program is not GDPR, NIST 800-122, nor ISO27001 compliant, although the author believes it can be made compliant with effort. Be sure to check local laws before using and before distributing reports.

## Features of Open Meeting Speaker Analyzer
-   **Links to Video**: All reports include links to the exact place where someone said something cited in a report so you can quickly jump to it and hear exactly what a person said. 
-   **Modular Architecture**: Includes connectors for City of Austin, City of Houston, and YouTube. Other connectors to different video sources can be created by anyone so you can perform analysis on any public meeting database that doesn't restrict downloads.
-   **Privacy Feature**: Optional masking of speaker names (--mask cli flag) so that you can share reports while maintaining the privacy of the speakers. 
-   **Local AI Analysis**: Connects to any local LLM provider that use adheres to the openAI API specification (e.g., LM Studio) for all AI anlaysis. Use whatever AI model runs on your GPU. All your data stays in your network; you're not sharing any information with a SaaS service.
-   **Flexible CLI**: Run phases (Download, Transcribe, Report) individually or all at once. Download the media once, report again and again even with different prompts to extract the most knowledge you can.
-   **Ad-hoc Questions**: In addition to the standard reports, you can ask any question you like of the knowledge base you've downloaded it, regardless of what was prompted in the reports.  Allows you to ask questions once you gain insights from the reports.  

## How Open Meeting Speaker Analyzer  Works

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

## Getting Started with Open Meeting Speaker Analyzer

### 1. Prerequisites & Model Access for Speaker Analyzer
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
This program was designed as a "Private AI". It assumes media files are downloaded from the public internet to a private network behind an industry standard firewall and that all analysis are done on GPU's located in the network behind that firewall. The intent is that all files stay within this private network. The connects to the Internet for two specific tasks: 1) downloading video files and 2) getting authorization from Hugging Face to use a transcription service on the local drive; this happens each time the program is run. In this way, all analysis and reporting is private.  The program doesn not enforce this requirement, so it's assumed that the user will use it that way. By using an encrypted hard drive for the media files, you may actually be able to pass some security certifications, but there are no guarantees. If this an issue, consult a compliance professional. Future versions may eliminate the need for getting validation every time from Hugging Face.  If you already have have a media database, you can point to it via defaults.yaml and not have to go out to the Internet.

### This Program Was Created wit Agentic AI ###
This program was created with Google Antigravity and agentic AI programming tool. It started as a human readable specification from which much of this README.md file came. The program was released on github nine days later. The iterative programming process consisted of running the program, seeing bugs, or a thinking up new functionality, and then communicating that to Antigravity.  

Sometimes the prompts for new functionality were simple, such as:
"Ensure that setup.sh installs all necessary dependencies."

Sometimes they were more complex:
"Just like the Austin City Council meeting archives, we're going to look at the Houston city council meeting archives.  While they use swagit as well and the screen format is very similar (if not identical), their agenda is a little different. The public comments section is not of a fixed length. Heres a sample web page of a Houston City Council Meeting:" and then details would follow.

What are the implications?  The iterative development was fast. However, no human has done a code review at the time the software was released.  

Antigravity was asked to review the code against GDPR, NIST 800-122, and ISO27001 certifications.  The code is not currently compliant, but probably could be made to be compliant with an additional develpment effort. Major new areas to be developed include, but are not limited to:
- encryption of data in motion and at rest.  This most likely means using https to talk to the LLM rather than http (or using a reverse proxy), and putting the data on an encrypted hard drive.
- More robust protection of speaker's privacy with 1) automatic name masking during the transcription phase, and 2) automatic deletion of media files after transcription is done.
- Integration with an existing ACL, or creation of an account system in order to control access.
- Robust access logging
- A mechanism to delete speaker's requests for deletion in order to meet GDPR requirements

Note that this list is most likely not complete.

Antigravity was also asked to a code license review of all the dependencies the program uses.  All dependencies were found to use licenses that were compatible with the existing license. This is what it reported: 

--- Begin Antigravity Output ---
The following dependencies were identified across 

requirements.txt,
system installation scripts (setup.sh), 
and dynamic Python imports. 

All identified licenses are compatible with AGPLv3:

### Python Dependencies (Explicit & Implicit)

|Dependency|License|AGPLv3 Compatible?|Notes|
|---|---|---|---|
|`requests`|Apache 2.0|Yes|Permissive|
|`beautifulsoup4`|MIT|Yes|Permissive|
|`pyyaml`|MIT|Yes|Permissive|
|`yt-dlp`|Unlicense|Yes|Public Domain equivalent|
|`chromadb`|Apache 2.0|Yes|Permissive|
|`numpy`|BSD 3-Clause|Yes|Permissive|
|`ctranslate2`|MIT|Yes|Permissive|
|`torchcodec`|BSD 3-Clause|Yes|Permissive|
|`torch` / `torchaudio`|BSD-style|Yes|Permissive|
|`whisperx`|BSD 2-Clause|Yes|Permissive|

### System & External Executables

| Dependency | License    | AGPLv3 Compatible? | Notes                   |
| ---------- | ---------- | ------------------ | ----------------------- |
| `ffmpeg`   | GPL / LGPL | Yes                | Called via `subprocess` |
| `whiptail` | GPL        | Yes                | Called in setup scripts |
--- End Antigravity Output ---

However, Antigravity noted a point of friction:

--- Begin Antigravity Output ---
While the software licenses are legally compatible, there is a significant discrepancy regarding the Pyannote Speaker Diarization model (pyannote/speaker-diarization-3.1) used dynamically by whisperx for speaker identification.

WARNING

Gated Model Access for Pyannote While pyannote.audio and its models are nominally licensed under the MIT License, the model weights are hosted on Hugging Face as a "Gated Model".

Why this is a discrepancy:

Access Restrictions: To download the model, users are strictly required to create a Hugging Face account, accept specific user conditions, and share their contact information with the Pyannote authors.

AGPLv3 Friction: AGPLv3 (Section 10) explicitly states: "You may not impose any further restrictions on the exercise of the rights granted or affirmed under this License." By tying a core functionality of speaker-analyzer to a component that restricts anonymous, automated downloading, the application introduces friction.

--- End Antigravity Output ---



research_results.md
../../brain/64281293-2292-4195-aa66-6afaa5dd4a06


# Desktop and Laptop Computers with GPUs (2024-2025)
The following is a sample list of current models from top manufacturers that include a GPU, with direct links to purchase them. Models highlighted with **(High Performance)** meet or exceed the performance of an **NVIDIA RTX A2000 (12GB)**, which serves as our baseline (~8.0 TFLOPS FP32).  This list is provided as a courtesty. It'll most certainly be out of date by the time you read this as the rate of change in computer hardware is so high. Also, none of these systems have been tested against this software, but the gauging buy the GPU performance numbers, they should run this program just fine.

---
## Desktop Computers
| Manufacturer | Model Series | GPU Options | Purchase Link | Performance Note |
| :--- | :--- | :--- | :--- | :--- |
| **Dell** | [Precision 3680 Tower](https://www.dell.com/en-us/shop/workstations/precision-3680-tower-workstation/spd/precision-3680-workstation) | NVIDIA RTX 2000-6000 Ada | [View on Dell](https://www.dell.com/en-us/shop/workstations/precision-3680-tower-workstation/spd/precision-3680-workstation) | **(High Performance)** |
| | [XPS Desktop](https://www.dell.com/en-us/shop/desktop-computers/xps-desktop/spd/xps-8960-desktop) | NVIDIA RTX 4060 - 4080 | [View on Dell](https://www.dell.com/en-us/shop/desktop-computers/xps-desktop/spd/xps-8960-desktop) | **(High Performance)** |
| | [Alienware Aurora R16](https://www.dell.com/en-us/shop/desktop-computers/alienware-aurora-r16-gaming-desktop/spd/alienware-aurora-r16-desktop) | NVIDIA RTX 4070 - 4090 | [View on Dell](https://www.dell.com/en-us/shop/desktop-computers/alienware-aurora-r16-gaming-desktop/spd/alienware-aurora-r16-desktop) | **(High Performance)** |
| **HP** | [Z2 G9 Tower](https://www.hp.com/us-en/shop/pdp/hp-z2-tower-g9-workstation-desktop-pc-customizable-5f0h0av-1) | NVIDIA RTX A2000 - A5000 | [View on HP](https://www.hp.com/us-en/shop/pdp/hp-z2-tower-g9-workstation-desktop-pc-customizable-5f0h0av-1) | **(High Performance)** |
| | [Omen 45L Gaming](https://www.hp.com/us-en/shop/pdp/omen-by-hp-45l-gaming-desktop-gt22-1455xt-bundle-7p3e2aa-aba-1) | NVIDIA RTX 4070 Ti - 4090 | [View on HP](https://www.hp.com/us-en/shop/pdp/omen-by-hp-45l-gaming-desktop-gt22-1455xt-bundle-7p3e2aa-aba-1) | **(High Performance)** |
| **Lenovo** | [ThinkStation P3](https://www.lenovo.com/us/en/p/workstations/thinkstation-p-series/thinkstation-p3-tower/len102s0015) | NVIDIA RTX 2000 - 5000 Ada | [View on Lenovo](https://www.lenovo.com/us/en/p/workstations/thinkstation-p-series/thinkstation-p3-tower/len102s0015) | **(High Performance)** |
| | [Legion Tower 7i](https://www.lenovo.com/us/en/p/desktops/legion-desktops/legion-t-series-towers/legion-tower-7i-gen-8-(intel)/len102g0002) | NVIDIA RTX 4080 - 4090 | [View on Lenovo](https://www.lenovo.com/us/en/p/desktops/legion-desktops/legion-t-series-towers/legion-tower-7i-gen-8-(intel)/len102g0002) | **(High Performance)** |
| **Apple** | [Mac Studio](https://www.apple.com/mac-studio/) | M2 Max / M2 Ultra | [View on Apple](https://www.apple.com/mac-studio/) | **(High Performance)** |
| | [Mac Pro](https://www.apple.com/mac-pro/) | M2 Ultra | [View on Apple](https://www.apple.com/mac-pro/) | **(High Performance)** |
| **ASUS** | [ROG Strix G16CH](https://rog.asus.com/desktops/mid-tower/rog-strix-g16ch-series/) | NVIDIA RTX 4070 - 4080 | [View on ASUS](https://rog.asus.com/desktops/mid-tower/rog-strix-g16ch-series/) | **(High Performance)** |
| **MSI** | [Infinite RS AI](https://www.msi.com/Desktop/Infinite-RS-14th) | NVIDIA RTX 4070 - 4090 | [View on MSI](https://www.msi.com/Desktop/Infinite-RS-14th) | **(High Performance)** |
| **Acer** | [Predator Orion 7000](https://www.acer.com/us-en/predator/desktops/orion/orion-7000) | NVIDIA RTX 4080 - 4090 | [View on Acer](https://www.acer.com/us-en/predator/desktops/orion/orion-7000) | **(High Performance)** |
---
## Laptop Computers
| Manufacturer | Model Series | GPU Options | Purchase Link | Performance Note |
| :--- | :--- | :--- | :--- | :--- |
| **Dell** | [Precision 5690](https://www.dell.com/en-us/shop/workstations/precision-5690-mobile-workstation/spd/precision-5690-laptop) | NVIDIA RTX 2000-5000 Ada | [View on Dell](https://www.dell.com/en-us/shop/workstations/precision-5690-mobile-workstation/spd/precision-5690-laptop) | **(High Performance)** |
| | [XPS 16](https://www.dell.com/en-us/shop/dell-laptops/xps-16-laptop/spd/xps-16-9640-laptop) | NVIDIA RTX 4050 - 4070 | [View on Dell](https://www.dell.com/en-us/shop/dell-laptops/xps-16-laptop/spd/xps-16-9640-laptop) | **(High Performance)** |
| **HP** | [ZBook Fury G11](https://www.hp.com/us-en/shop/pdp/hp-zbook-fury-16-g11-mobile-workstation-pc-customizable-946u0av-1) | NVIDIA RTX 3500-5000 Ada | [View on HP](https://www.hp.com/us-en/shop/pdp/hp-zbook-fury-16-g11-mobile-workstation-pc-customizable-946u0av-1) | **(High Performance)** |
| | [Omen Transcend 16](https://www.hp.com/us-en/shop/pdp/omen-transcend-laptop-16t-u100-161-8t4j2av-1) | NVIDIA RTX 4070 | [View on HP](https://www.hp.com/us-en/shop/pdp/omen-transcend-laptop-16t-u100-161-8t4j2av-1) | **(High Performance)** |
| **Lenovo** | [ThinkPad P1 Gen 7](https://www.lenovo.com/us/en/p/laptops/thinkpad/thinkpadp/thinkpad-p1-gen-7-(16-inch-intel)/len101t0105) | NVIDIA RTX 1000-3000 Ada | [View on Lenovo](https://www.lenovo.com/us/en/p/laptops/thinkpad/thinkpadp/thinkpad-p1-gen-7-(16-inch-intel)/len101t0105) | **(High Performance)** |
| | [Legion Pro 7i](https://www.lenovo.com/us/en/p/laptops/legion-laptops/legion-pro-series/legion-pro-7i-gen-8-(16-inch-intel)/len101g0023) | NVIDIA RTX 4080 - 4090 | [View on Lenovo](https://www.lenovo.com/us/en/p/laptops/legion-laptops/legion-pro-series/legion-pro-7i-gen-8-(16-inch-intel)/len101g0023) | **(High Performance)** |
| **Apple** | [MacBook Pro (M4)](https://www.apple.com/shop/buy-mac/macbook-pro) | M4 Pro / M4 Max | [View on Apple](https://www.apple.com/shop/buy-mac/macbook-pro) | **(High Performance)** |
| **ASUS** | [ROG Zephyrus G16](https://rog.asus.com/laptops/rog-zephyrus/rog-zephyrus-g16-2024/) | NVIDIA RTX 4070 - 4090 | [View on ASUS](https://rog.asus.com/laptops/rog-zephyrus/rog-zephyrus-g16-2024/) | **(High Performance)** |
| **MSI** | [Titan 18 HX AI](https://www.msi.com/Laptop/Titan-18-HX-A14VX) | NVIDIA RTX 4080 - 4090 | [View on MSI](https://www.msi.com/Laptop/Titan-18-HX-A14VX) | **(High Performance)** |
| **Acer** | [Predator Helios 18](https://www.acer.com/us-en/predator/laptops/helios/helios-18) | NVIDIA RTX 4080 - 4090 | [View on Acer](https://www.acer.com/us-en/predator/laptops/helios/helios-18) | **(High Performance)** |
---
### Performance Baseline Note: NVIDIA RTX A2000 (12GB)
The **RTX A2000 12GB** is a professional workstation card based on the Ampere architecture (~8.0 TFLOPS FP32).
**Comparison Thresholds for High Performance:**
- **NVIDIA Desktop:** RTX 3060, RTX 4060, and higher models.
- **NVIDIA Laptop:** RTX 4050 Laptop and higher (due to generational efficiency).
- **Apple Silicon:** M3 Max and all M4 Pro/Max variants.
- **Professional:** RTX 2000 Ada and higher models.
