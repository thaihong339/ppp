# -*- coding: utf-8 -*-
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

# --- Cách 2: Tách token GitHub / GitLab từ 1 biến GITLAB_GITHUB ---
ALL_TOKENS = os.getenv("GITLAB_GITHUB", "")
if not ALL_TOKENS:
    raise ValueError("Thiếu biến môi trường GITLAB_GITHUB")

tokens = [t.strip() for t in ALL_TOKENS.split(",") if t.strip()]
github_tokens = [t for t in tokens if t.startswith("ghp_")]
gitlab_tokens = [t for t in tokens if t.startswith("glpat-")]

if not github_tokens:
    raise ValueError("Không tìm thấy GitHub token trong GITLAB_GITHUB")
if not gitlab_tokens:
    raise ValueError("Không tìm thấy GitLab token trong GITLAB_GITHUB")

github_cycle = itertools.cycle(github_tokens)
gitlab_cycle = itertools.cycle(gitlab_tokens)

# --- Setup ---
save_dir = Path(__file__).resolve().parent / "found_keybox"
save_dir.mkdir(parents=True, exist_ok=True)
cache_file = Path(__file__).resolve().parent / "cache.txt"
cached_urls = set(open(cache_file).readlines()) if cache_file.exists() else set()

search_terms = [
    "<AndroidAttestation>",
    "<NumberOfCertificates>3</NumberOfCertificates>",
    "</CertificateChain>",
]

session = requests.Session()
GITHUB_GQL = "https://api.github.com/graphql"
GITLAB_SEARCH_API = "https://gitlab.com/api/v4/search"

total_count = 0

def save_keybox(content):
    global total_count
    try:
        root = etree.fromstring(content)
        canonical = etree.tostring(root, method="c14n")
        hash_val = hashlib.sha256(canonical).hexdigest()
        fpath = save_dir / (hash_val + ".xml")
        if not fpath.exists():
            with open(fpath, "wb") as f:
                f.write(content)
            total_count += 1
            print(f"{Fore.GREEN}Lưu mới: {fpath.name}")
    except:
        return

def github_query(term):
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
    }}
    '''
    current_token = next(github_cycle)
    headers = {
        "Authorization": f"bearer {current_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    r = session.post(GITHUB_GQL, json={"query": query}, headers=headers)
    if r.status_code != 200:
        print(f"{Fore.YELLOW}[GitHub] Lỗi {r.status_code}, đợi 10s...")
        time.sleep(10)
        return []
    return r.json().get("data", {}).get("search", {}).get("nodes", [])

def gitlab_search(term):
    results = []
    for page in range(1, 5):
        current_token = next(gitlab_cycle)
        params = {
            "scope": "blobs",
            "search": term,
            "per_page": 20,
            "page": page
        }
        headers = {
            "PRIVATE-TOKEN": current_token
        }
        r = session.get(GITLAB_SEARCH_API, headers=headers, params=params)
        if r.status_code == 429:
            print(f"{Fore.YELLOW}[GitLab] Rate limit hit. Waiting 10s...")
            time.sleep(10)
            continue
        if r.status_code != 200:
            break
        results += r.json()
    return results

def fetch_url_content(url):
    r = session.get(url)
    return r.content if r.status_code == 200 else None

def search_github():
    for term in search_terms:
        print(f"\n{BOLD}[GitHub] Đang tìm: {term}")
        results = github_query(term)
        for item in results:
            repo = item["repository"]["nameWithOwner"]
            path = item["path"]
            raw_url = f"https://raw.githubusercontent.com/{repo}/HEAD/{path}"
            if raw_url + "\n" in cached_urls:
                continue
            cached_urls.add(raw_url + "\n")
            content = fetch_url_content(raw_url)
            if content:
                save_keybox(content)

def search_gitlab():
    for term in search_terms:
        print(f"\n{BOLD}[GitLab] Đang tìm: {term}")
        results = gitlab_search(term)
        for item in results:
            file_url = item.get("url")
            if not file_url or file_url + "\n" in cached_urls:
                continue
            cached_urls.add(file_url + "\n")
            raw_url = file_url.replace("gitlab.com/", "gitlab.com/-/raw/")
            content = fetch_url_content(raw_url)
            if content:
                save_keybox(content)

# --- Main ---
search_github()
search_gitlab()

open(cache_file, "w").writelines(cached_urls)
print(f"\n{BOLD}Tổng số keybox đã lưu: {total_count}")
