import hashlib
import os
from pathlib import Path
import requests
from dotenv import load_dotenv
from lxml import etree
import json
import subprocess
import logging
from colorama import Fore, Style, init
import itertools

# Initialize colorama
init(autoreset=True)
BOLD = Style.BRIGHT
session = requests.Session()

# Load environment variables from .env file
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
    "</CertificateChain>"
]

save = Path(__file__).resolve().parent / "found_keybox"
save.mkdir(parents=True, exist_ok=True)

cache_file = Path(__file__).resolve().parent / "cache.txt"
if cache_file.exists():
    cached_urls = set(open(cache_file, "r").readlines())
else:
    cached_urls = set()

total_keybox_count = 0
keybox_urls = {}

logging.basicConfig(level=logging.INFO, format='%(message)s')

def fetch_file_content(url: str) -> bytes:
    response = session.get(url)
    if response.status_code == 200:
        return response.content
    else:
        raise RuntimeError(f"Không thể tải file {url}")

def fetch_and_process_results(search_url: str, page: int) -> bool:
    global total_keybox_count
    params = {"per_page": 100, "page": page}
    current_token = next(token_cycle)
    headers = {
        "Authorization": f"token {current_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    response = session.get(search_url, headers=headers, params=params)
    if response.status_code != 200:
        raise RuntimeError(f"Không thể lấy kết quả tìm kiếm: {response.status_code}")
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
                except etree.XMLSyntaxError:
                    continue
                canonical_xml = etree.tostring(root, method="c14n")
                hash_value = hashlib.sha256(canonical_xml).hexdigest()
                file_name_save = save / (hash_value + ".xml")
                if not file_name_save.exists():
                    print(f"{raw_url} là file mới")
                    with open(file_name_save, "wb") as f:
                        f.write(file_content)
                    total_keybox_count += 1
                    keybox_urls[file_name_save] = raw_url
                    print(f"Đã lưu file keybox: {file_name_save.name}")
    return len(search_results["items"]) > 0

# Main loop
for query in search_queries:
    print(f"Đang tìm kiếm với truy vấn: {query}")
    search_url = f"https://api.github.com/search/code?q={query}"
    page = 1
    while fetch_and_process_results(search_url, page):
        page += 1

# Cập nhật cache
open(cache_file, "w").writelines(cached_urls)

print(f"\nTổng số keybox đã lưu vào 'found_keybox': {total_keybox_count}")
