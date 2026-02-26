import sys
from utils.logger import Logger
from utils.file_manager import FileManager
from connectors.dallas_connect import DallasConnector

log = Logger()
fm = FileManager()
connector = DallasConnector(log, fm)

urls = [
    "https://dallastx.new.swagit.com/videos/374900?segment=1",
    "https://dallastx.new.swagit.com/videos/374900?segment=2",
    "https://dallastx.new.swagit.com/videos/274274?segment=1"
]

for title, url in enumerate(urls, 1):
    print(f"\nTesting URL {title}: {url}")
    meta = connector.get_metadata(url)
    print(meta)
