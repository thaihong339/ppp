# Option 3: keybox_search_graphql.py
# Uses GitHub GraphQL API for more efficient querying with token rotation

import hashlib
import os
from pathlib import Path
import requests
from dotenv import load_dotenv
from lxml import etree
import itertools
from colorama import Fore, Style, init
import time

init(autoreset=True)
BOLD = Style.BRIGHT

load_dotenv()
GITHUB_TOKENS = os.getenv("MY_GITHUB_TOKEN")
if not GITHUB_TOKENS:
    raise ValueError("MY_GITHUB_TOKEN is not set in the .env file")

tokens = [token.strip() for token in GITHUB_TOKENS.split(",") if token.strip()]
if not tokens:
    raise ValueError("Danh sách MY_GITHUB_TOKEN rỗng hoặc không hợp lệ")

token_cycle = itertools.cycle(tokens)
save = Path(__file__).resolve().parent / "found_keybox"
save.mkdir(parents=True, exist_ok=True)

cache_file = Path(__file__).resolve().parent / "cache.txt"
cached_urls = set(open(cache_file).readlines()) if cache_file.exists() else set()
total_keybox_count = 0

search_terms = [
    "<AndroidAttestation>",
    "<CertificateChain>",
    "</CertificateChain>",
    "</Keybox>",
    "</NumberOfCertificates>"
]

GQL_API = "https://api.github.com/graphql"

session = requests.Session()

def graphql_query(query):
    current_token = next(token_cycle)
    headers = {
        "Authorization": f"bearer {current_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    r = session.post(GQL_API, json={"query": query}, headers=headers)
    if r.status_code != 200:
        print(f"GQL error {r.status_code}, sleeping 10s...")
        time.sleep(10)
        return None
    return r.json()

def fetch_file_content(url):
    r = session.get(url)
    return r.content if r.status_code == 200 else None

def search_code(term):
    global total_keybox_count
    query = f'''
    {{
      search(query: "{term} extension:xml", type: CODE, first: 100) {{
        nodes {{
          ... on CodeSearchResultItem {{
            repository {{ nameWithOwner }}
            path
          }}
        }}
      }}
    }}'''
    result = graphql_query(query)
    if not result:
        return
    items = result.get("data", {}).get("search", {}).get("nodes", [])
    for item in items:
        repo = item["repository"]["nameWithOwner"]
        path = item["path"]
        raw_url = f"https://raw.githubusercontent.com/{repo}/HEAD/{path}"
        if raw_url + "\n" in cached_urls:
            continue
        cached_urls.add(raw_url + "\n")
        content = fetch_file_content(raw_url)
        if not content:
            continue
        try:
            root = etree.fromstring(content)
        except:
            continue
        canonical = etree.tostring(root, method="c14n")
        hash_val = hashlib.sha256(canonical).hexdigest()
        fpath = save / (hash_val + ".xml")
        if not fpath.exists():
            with open(fpath, "wb") as f:
                f.write(content)
            total_keybox_count += 1
            print(f"{Fore.GREEN}Lưu mới: {fpath.name}")

for term in search_terms:
    print(f"\n{BOLD}GraphQL Search: {term}")
    search_code(term)

open(cache_file, "w").writelines(cached_urls)
print(f"\nTổng số keybox: {total_keybox_count}")
