usage: speaker-analyzer.py  --url URL | --batch textfile  [options...]

options:
  -h, --help        show this help message and exit
  --url URL         Download the media in the URL
  --batch textfile  Download all the media in a text file. "#" is a comment.
  --audio           (Default) Download only audio and exit.
  --video           Download video and audio and exit
  --transcribe      Only transcribe the text from the audio and then exit.
                    Reports if there are no media files to transcribe.
  --report          Generate final report only. Reports if there are no
                    transcriptions.
  --all             (Default). Go through all phases in order: download media,
                    transcribe, report.
  --force           Force overwriting files. Program default is not to
                    overwrite existing files
  --mask            Mask the names of speakers with a one way hash.
  -v, --verbose     Enable verbose logging to screen and log file of detailed
                    processing steps for debugging.

Notes:
  The source of truth for all paths is configs/defaults.yaml. 
  The LLM prompt and keywords are in configs/prompts.yaml.
  See README.md and DEPLOYMENT.md for technical requirements.
  Software provide as-is. No warranty expressed nor implied.
