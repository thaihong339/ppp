import requests
import time
import os
from urllib.parse import quote

# Nạp GitLab tokens từ biến môi trường
tokens = [t.strip() for t in os.getenv("GITLAB_TOKENS", "").split(",")]
search_limit = 100  # Giới hạn số repo để demo

def get_repos(token, search_term="android", max_repos=search_limit):
    headers = {"PRIVATE-TOKEN": token}
    repos = []
    page = 1

    while len(repos) < max_repos:
        url = f"https://gitlab.com/api/v4/search?scope=projects&search={quote(search_term)}&per_page=50&page={page}"
        resp = requests.get(url, headers=headers)
        if resp.status_code == 403:
            print("GitLab bị 403, đợi 5s...")
            time.sleep(5)
            continue
        elif resp.status_code != 200:
            print(f"Error {resp.status_code}: {resp.text}")
            break

        results = resp.json()
        if not results:
            break

        repos.extend(results)
        if len(results) < 50:
            break
        page += 1

    return repos[:max_repos]

def find_keybox_files(repo, token):
    headers = {"PRIVATE-TOKEN": token}
    project_id = repo["id"]

    url = f"https://gitlab.com/api/v4/projects/{project_id}/repository/tree?recursive=true&per_page=100"
    resp = requests.get(url, headers=headers)

    if resp.status_code != 200:
        return []

    files = resp.json()
    matches = []
    for f in files:
        if f["type"] == "blob" and "keybox" in f["path"].lower() and f["path"].lower().endswith(".xml"):
            matches.append(f["path"])
    return matches

# Dò token hợp lệ
for token in tokens:
    print(f"Đang dùng token: {token[:8]}...")
    repos = get_repos(token)
    total_found = 0

    for repo in repos:
        files = find_keybox_files(repo, token)
        if files:
            print(f"\n📦 {repo['path_with_namespace']}")
            for f in files:
                print("   →", f)
                total_found += 1

    print(f"\n✅ Tổng số file keybox XML tìm được: {total_found}")
    break  # Dùng 1 token là đủ, tránh lặp nhiều
