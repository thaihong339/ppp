# keybox_search_gitgraph.py
# GitHub GraphQL + GitLab REST combined keybox searcher

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
GITLAB_TOKEN = os.getenv("MY_GITLAB_TOKEN")
if not GITHUB_TOKENS:
    raise ValueError("MY_GITHUB_TOKEN is not set")

tokens = [t.strip() for t in GITHUB_TOKENS.split(",") if t.strip()]
if not tokens:
    raise ValueError("GITHUB token list empty")
token_cycle = itertools.cycle(tokens)

save = Path(__file__).resolve().parent / "found_keybox"
save.mkdir(parents=True, exist_ok=True)

cache_file = Path(__file__).resolve().parent / "cache.txt"
cached_urls = set(open(cache_file).readlines()) if cache_file.exists() else set()
total_keybox_count = 0

search_terms = [
    "<AndroidAttestation>",
    "<NumberOfCertificates>3</NumberOfCertificates>",
    "</CertificateChain>",
]

GQL_API = "https://api.github.com/graphql"
GITLAB_SEARCH = "https://gitlab.com/api/v4/search"

session = requests.Session()

def graphql_query(query):
    current_token = next(token_cycle)
    headers = {
        "Authorization": f"bearer {current_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    r = session.post(GQL_API, json={"query": query}, headers=headers)
    if r.status_code != 200:
        print(f"GitHub GraphQL error {r.status_code}, sleeping...")
        time.sleep(10)
        return None
    return r.json()

def fetch_file_content(url, headers=None):
    r = session.get(url, headers=headers)
    return r.content if r.status_code == 200 else None

def save_keybox(raw_url, content):
    global total_keybox_count
    try:
        root = etree.fromstring(content)
    except:
        return
    canonical = etree.tostring(root, method="c14n")
    hash_val = hashlib.sha256(canonical).hexdigest()
    fpath = save / (hash_val + ".xml")
    if not fpath.exists():
        with open(fpath, "wb") as f:
            f.write(content)
        total_keybox_count += 1
        print(f"{Fore.GREEN}Lưu mới: {fpath.name}")

def github_search(term):
    print(f"\n{BOLD}GitHub: {term}")
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
        if content:
            save_keybox(raw_url, content)

def gitlab_search(term):
    if not GITLAB_TOKEN:
        print("GITLAB token not set, skipping GitLab")
        return
    print(f"\n{BOLD}GitLab: {term}")
    headers = {"Private-Token": GITLAB_TOKEN}
    for page in range(1, 6):  # Limit pages
        params = {"scope": "blobs", "search": term, "per_page": 20, "page": page}
        r = session.get(GITLAB_SEARCH, headers=headers, params=params)
        if r.status_code != 200:
            print(f"GitLab error {r.status_code}")
            break
        results = r.json()
        for item in results:
            project_id = item.get("project_id")
            file_path = item.get("path")
            if not project_id or not file_path:
                continue
            raw_url = f"https://gitlab.com/api/v4/projects/{project_id}/repository/files/{requests.utils.quote(file_path, safe='')}/raw?ref=master"
            if raw_url + "\n" in cached_urls:
                continue
            cached_urls.add(raw_url + "\n")
            content = fetch_file_content(raw_url, headers=headers)
            if content:
                save_keybox(raw_url, content)

for term in search_terms:
    github_search(term)
    gitlab_search(term)

open(cache_file, "w").writelines(cached_urls)
print(f"\nTổng số keybox: {total_keybox_count}")
