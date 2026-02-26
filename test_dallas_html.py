from bs4 import BeautifulSoup
import requests

url = "https://dallastx.new.swagit.com/videos/374900"
response = requests.get(url)
soup = BeautifulSoup(response.text, 'html.parser')
items = soup.select('#video-index-sm .playerControl[data-title]')

for i, item in enumerate(items):
    title = item.get('data-title', '').strip().upper()
    if "OPEN MICROPHONE" in title:
        print(f"Index: {i}, Title: {title}, Start: {item.get('data-ts')}, End: {item.get('data-end-ts')}")
        if i + 1 < len(items):
            print(f"  Next Item: {items[i+1].get('data-title', '').strip().upper()}, Start: {items[i+1].get('data-ts')}")
