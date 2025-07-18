import os
import requests
import hashlib
import itertools
from pathlib import Path
from dotenv import load_dotenv
from colorama import Fore, Style, init
import time

init(autoreset=True)
BOLD = Style.BRIGHT

# Load token từ .env
load_dotenv()
GITLAB_TOKENS = os.getenv("GITLAB_TOKENS")
if not GITLAB_TOKENS:
    raise ValueError("Thiếu biến môi trường GITLAB_TOKENS")

tokens = [t.strip() for t in GITLAB_TOKENS.split(",") if t.strip()]
if not tokens:
    raise ValueError("Danh sách token GitLab rỗng.")
token_cycle = itertools.cycle(tokens)

session = requests.Session()
BASE_API = "https://gitlab.com/api/v4"
RAW_BASE = "https://gitlab.com"

# Cache và thư mục lưu file
save_dir = Path(__file__).resolve().parent / "found_keybox"
save_dir.mkdir(exist_ok=True)
cache_file = Path(__file__).resolve().parent / "gitlab_cache.txt"
cached_urls = set(open(cache_file).readlines()) if cache_file.exists() else set()

def get_with_retry(url):
    for _ in range(5):
        token = next(token_cycle)
        headers = {"PRIVATE-TOKEN": token}
        r = session.get(url, headers=headers)
        if r.status_code == 403:
            print(f"{Fore.YELLOW}GitLab lỗi 403, đợi 5s...")
            time.sleep(5)
            continue
        if r.status_code == 200:
            return r.json()
        break
    return None

def fetch_raw_file(project_id, path, ref='master'):
    url = f"{BASE_API}/projects/{project_id}/repository/files/{requests.utils.quote(path, safe='')}/raw?ref={ref}"
    token = next(token_cycle)
    headers = {"PRIVATE-TOKEN": token}
    r = session.get(url, headers=headers)
    return r.content if r.status_code == 200 else None

def search_gitlab_keybox():
    page = 1
    total_saved = 0
    print(f"{BOLD}\n=== GitLab Keybox Search ===")
    while True:
        url = f"{BASE_API}/search?scope=blobs&search=keybox&page={page}&per_page=50"
        results = get_with_retry(url)
        if not results:
            break
        for item in results:
            project = item.get("project_id")
            path = item.get("path")
            if not project or not path:
                continue
            raw_url = f"{RAW_BASE}/{item['project_path']}/-/raw/master/{path}"
            if raw_url + "\n" in cached_urls:
                continue
            cached_urls.add(raw_url + "\n")
            content = fetch_raw_file(project, path)
            if not content:
                continue
            try:
                hash_val = hashlib.sha256(content).hexdigest()
                fpath = save_dir / f"{hash_val}.xml"
                if not fpath.exists():
                    with open(fpath, "wb") as f:
                        f.write(content)
                    print(f"{Fore.GREEN}Lưu file mới: {fpath.name}")
                    total_saved += 1
            except Exception as e:
                print(f"{Fore.RED}Lỗi khi lưu: {e}")
        page += 1
        if len(results) < 50:
            break

    open(cache_file, "w").writelines(cached_urls)
    print(f"{BOLD}\nTổng số keybox đã lưu: {total_saved}")

if __name__ == "__main__":
    search_gitlab_keybox()
