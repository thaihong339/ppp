# -*- coding: utf-8 -*-
# @Author: ChatGPT (Updated 2025-07)
# Combines GitHub GraphQL & GitLab REST for mass keybox scanning

import os
import time
import hashlib
import itertools
from pathlib import Path
from dotenv import load_dotenv
import requests
from lxml import etree
from colorama import Fore, Style, init

init(autoreset=True)
BOLD = Style.BRIGHT

# ─── Load Env ────────────────────────────────────────────────
load_dotenv()
GITHUB_TOKENS = os.getenv("MY_GITHUB_TOKEN")
GITLAB_TOKENS = os.getenv("GITLAB_TOKENS")

if not GITHUB_TOKENS or not GITLAB_TOKENS:
    raise ValueError("Thiếu biến môi trường GITHUB_TOKENS hoặc GITLAB_TOKENS")

gh_tokens = [t.strip() for t in GITHUB_TOKENS.split(",") if t.strip()]
gl_tokens = [t.strip() for t in GITLAB_TOKENS.split(",") if t.strip()]
gh_token_cycle = itertools.cycle(gh_tokens)
gl_token_cycle = itertools.cycle(gl_tokens)

# ─── Setup ───────────────────────────────────────────────────
session = requests.Session()
GQL_API = "https://api.github.com/graphql"
search_terms = [
    "<AndroidAttestation>",
    "<NumberOfCertificates>3</NumberOfCertificates>",
    "</CertificateChain>",
]

save_dir = Path(__file__).resolve().parent / "found_keybox"
save_dir.mkdir(exist_ok=True)

cache_file = Path(__file__).resolve().parent / "cache.txt"
cached_urls = set(open(cache_file).readlines()) if cache_file.exists() else set()

total_saved = 0

# ─── Helper: Canonical Save ──────────────────────────────────
def save_keybox(url, content, canonical):
    global total_saved
    h = hashlib.sha256(canonical).hexdigest()
    fpath = save_dir / f"{h}.xml"
    if not fpath.exists():
        with open(fpath, "wb") as f:
            f.write(content)
        total_saved += 1
        print(f"{Fore.GREEN}→ Đã lưu mới: {fpath.name}")
    cached_urls.add(url + "\n")

def fetch_and_parse_xml(url):
    try:
        r = session.get(url)
        if r.status_code != 200:
            return None
        root = etree.fromstring(r.content)
        canonical = etree.tostring(root, method="c14n")
        return r.content, canonical
    except:
        return None

# ─── GitHub GraphQL Search ──────────────────────────────────
def github_graphql_search():
    print(f"\n{BOLD}=== GitHub (GraphQL) ===")
    for term in search_terms:
        print(f"{BOLD}→ Tìm: {term}")
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
        token = next(gh_token_cycle)
        headers = {
            "Authorization": f"bearer {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        r = session.post(GQL_API, json={"query": query}, headers=headers)
        if r.status_code != 200:
            print(f"{Fore.YELLOW}GitHub lỗi {r.status_code}, đợi 10s...")
            time.sleep(10)
            continue
        results = r.json().get("data", {}).get("search", {}).get("nodes", [])
        for item in results:
            repo = item["repository"]["nameWithOwner"]
            path = item["path"]
            raw_url = f"https://raw.githubusercontent.com/{repo}/HEAD/{path}"
            if raw_url + "\n" in cached_urls:
                continue
            parsed = fetch_and_parse_xml(raw_url)
            if parsed:
                raw, canonical = parsed
                save_keybox(raw_url, raw, canonical)

# ─── GitLab Blob Search ─────────────────────────────────────
def gitlab_search():
    print(f"\n{BOLD}=== GitLab ===")
    for term in search_terms:
        print(f"{BOLD}→ Tìm: {term}")
        for page in range(1, 5):
            token = next(gl_token_cycle)
            headers = {"Private-Token": token}
            url = f"https://gitlab.com/api/v4/search?scope=blobs&search={term}&per_page=20&page={page}"
            r = session.get(url, headers=headers)
            if r.status_code != 200:
                print(f"{Fore.YELLOW}GitLab lỗi {r.status_code}, đợi 5s...")
                time.sleep(5)
                continue
            results = r.json()
            if not results:
                break
            for res in results:
                if res.get("path", "").endswith(".xml") and "project_id" in res:
                    raw_url = f"https://gitlab.com/{res['project_path']}/-/raw/master/{res['path']}"
                    if raw_url + "\n" in cached_urls:
                        continue
                    parsed = fetch_and_parse_xml(raw_url)
                    if parsed:
                        raw, canonical = parsed
                        save_keybox(raw_url, raw, canonical)

# ─── Run ─────────────────────────────────────────────────────
if __name__ == "__main__":
    github_graphql_search()
    gitlab_search()
    with open(cache_file, "w") as f:
        f.writelines(cached_urls)
    print(f"\n{BOLD}Tổng số keybox đã lưu: {total_saved}")
