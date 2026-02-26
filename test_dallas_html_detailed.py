from bs4 import BeautifulSoup
import requests

urls = [
    "https://dallastx.new.swagit.com/videos/374900",
    "https://dallastx.new.swagit.com/videos/358889",
    "https://dallastx.new.swagit.com/videos/364137"
]

for url in urls:
    print(f"\n--- Testing URL {url} ---")
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    items = soup.select('#video-index-sm .playerControl[data-title]')

    for i, item in enumerate(items):
        title = item.get('data-title', '').strip().upper()
        ts_val = item.get('data-ts', '0')
        if not ts_val: ts_val = '0'
        start_ts = int(float(ts_val))
        if "OPEN MICROPHONE" in title:
            print(f"Index: {i}, Title: {title}, Start: {start_ts}, End: {item.get('data-end-ts')}")
