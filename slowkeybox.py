# Option 1: keybox_search_with_delay.py
# Adds delay to respect GitHub Search API's rate limit

import time
import hashlib
import os
from pathlib import Path
import requests
from dotenv import load_dotenv
from lxml import etree
import itertools
from colorama import Fore, Style, init

init(autoreset=True)
BOLD = Style.BRIGHT
session = requests.Session()

load_dotenv()
GITHUB_TOKENS = os.getenv("MY_GITHUB_TOKEN")
if not GITHUB_TOKENS:
    raise ValueError("MY_GITHUB_TOKEN is not set in the .env file")

tokens = [token.strip() for token in GITHUB_TOKENS.split(",") if token.strip()]
if not tokens:
    raise ValueError("Danh sách MY_GITHUB_TOKEN rỗng hoặc không hợp lệ")

token_cycle = itertools.cycle(tokens)

search_queries = [
    "<AndroidAttestation>",
    "<CertificateChain>",
    "</CertificateChain>",
    "</Keybox>",
    "</NumberOfCertificates>"
]

save = Path(__file__).resolve().parent / "found_keybox"
save.mkdir(parents=True, exist_ok=True)

cache_file = Path(__file__).resolve().parent / "cache.txt"
cached_urls = set(open(cache_file).readlines()) if cache_file.exists() else set()

total_keybox_count = 0

def fetch_file_content(url):
    response = session.get(url)
    if response.status_code == 200:
        return response.content
    else:
        raise RuntimeError(f"Không thể tải file {url}")

def fetch_and_process_results(search_url, page):
    global total_keybox_count
    params = {"per_page": 100, "page": page}
    current_token = next(token_cycle)
    headers = {
        "Authorization": f"token {current_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    response = session.get(search_url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Lỗi {response.status_code}, dửng trong 10s")
        time.sleep(10)
        return False
    search_results = response.json()
    if "items" in search_results:
        for item in search_results["items"]:
            file_name = item["name"]
            if file_name.lower().endswith(".xml"):
                raw_url = item["html_url"].replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
                if raw_url + "\n" in cached_urls:
                    continue
                cached_urls.add(raw_url + "\n")
                file_content = fetch_file_content(raw_url)
                try:
                    root = etree.fromstring(file_content)
                except:
                    continue
                canonical_xml = etree.tostring(root, method="c14n")
                hash_value = hashlib.sha256(canonical_xml).hexdigest()
                file_path = save / (hash_value + ".xml")
                if not file_path.exists():
                    print(f"Tìm thấy mới: {raw_url}")
                    with open(file_path, "wb") as f:
                        f.write(file_content)
                    total_keybox_count += 1
    return len(search_results.get("items", [])) > 0

for query in search_queries:
    print(f"\n{BOLD}Truy vấn: {query}")
    page = 1
    search_url = f"https://api.github.com/search/code?q={query}"
    while fetch_and_process_results(search_url, page):
        page += 1
        time.sleep(2)  # Delay added here

open(cache_file, "w").writelines(cached_urls)
print(f"\nTổng số file keybox: {total_keybox_count}")
