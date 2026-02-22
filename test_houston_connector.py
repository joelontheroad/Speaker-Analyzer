import sys
import os

# Add the project root to the path so we can import modules
sys.path.append(os.getcwd())

from connectors.houston_connect import HoustonConnector
from utils.logger import Logger
from utils.file_manager import FileManager

def test_houston_metadata():
    print("Testing Houston Connector Metadata Extraction...")
    log = Logger(verbose=True)
    fm = FileManager()
    connector = HoustonConnector(log, fm)
    
    url = "https://houstontx.new.swagit.com/videos/320673?ts=10190.705"
    
    print(f"URL: {url}")
    if connector.can_handle(url):
        print("Success: Connector can handle URL.")
    else:
        print("Failure: Connector cannot handle URL.")
        return

    meta = connector.get_metadata(url)
    
    if meta:
        print("\nMetadata Extracted successfully:")
        print(f"Title:    {meta.get('title')}")
        print(f"Date:     {meta.get('date')}")
        print(f"Offset:   {meta.get('offset')}s")
        print(f"Duration: {meta.get('duration')}s")
        print(f"Media URL: {meta.get('media_url')}")
        
        # Validation based on user-provided sample analysis
        # PUBLIC SPEAKERS start time: 1405 seconds
        # RECESS start time: 11074 seconds
        # Duration: 9669 seconds
        
        expected_offset = 1405
        expected_duration = 9669
        
        if meta.get('offset') == expected_offset:
            print(f"✅ Offset matches expected {expected_offset}")
        else:
            print(f"❌ Offset {meta.get('offset')} does NOT match expected {expected_offset}")

        if meta.get('duration') == expected_duration:
            print(f"✅ Duration matches expected {expected_duration}")
        else:
            print(f"❌ Duration {meta.get('duration')} does NOT match expected {expected_duration}")
            
        if meta.get('media_url') and (".m3u8" in meta.get('media_url') or ".mp4" in meta.get('media_url')):
            print("✅ Media URL looks valid.")
        else:
            print("❌ Media URL looks invalid.")
    else:
        print("Failure: Metadata extraction returned None.")

if __name__ == "__main__":
    test_houston_metadata()
