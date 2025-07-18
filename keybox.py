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
from cryptography import x509
import tempfile

# Initialize colorama
init(autoreset=True)

# ANSI escape codes for bold text
BOLD = Style.BRIGHT

session = requests.Session()

# Load environment variables from .env file
load_dotenv()
GITHUB_TOKENS = os.getenv("MY_GITHUB_TOKEN")

if not GITHUB_TOKENS:
    raise ValueError("MY_GITHUB_TOKEN is not set in the .env file")

# Tách các token thành danh sách
tokens = [token.strip() for token in GITHUB_TOKENS.split(",") if token.strip()]
if not tokens:
    raise ValueError("Danh sách MY_GITHUB_TOKEN rỗng hoặc không hợp lệ")

import itertools
# Tạo vòng lặp luân phiên các token
token_cycle = itertools.cycle(tokens)

# Danh sách các truy vấn tìm kiếm
search_queries = [
    "<AndroidAttestation>",
    "keybox",
    "strong integrity",
    # Bạn có thể thêm các truy vấn liên quan khác ở đây
]

# Headers cho yêu cầu API
# headers sẽ được tạo động trong hàm fetch_and_process_results

save = Path(__file__).resolve().parent / "keys"
save.mkdir(parents=True, exist_ok=True)  # Ensure the keys directory exists
cache_file = Path(__file__).resolve().parent / "cache.txt"

if cache_file.exists():
    cached_urls = set(open(cache_file, "r").readlines())
else:
    cached_urls = set()

# Bộ đếm tổng số keybox tìm thấy
total_keybox_count = 0

# Lưu trữ URL của các keybox đã tìm thấy
keybox_urls = {}

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Constants
CRL_URL = 'https://android.googleapis.com/attestation/status'
TIMEOUT = 10

def fetch_crl(url: str, timeout: int = TIMEOUT) -> dict:
    """Fetch Certificate Revocation List (CRL) with cache and cookies disabled."""
    try:
        process = subprocess.Popen(['curl', '-s', url], stdout=subprocess.PIPE)
        output, _ = process.communicate()
        crl = json.loads(output)
        return crl
    except Exception as e:
        logging.error(f"Failed to fetch or parse CRL: {e}")
        return {}

crl = fetch_crl(CRL_URL)
if not crl:
    logging.critical("Unable to proceed without a valid CRL.")
    exit(1)

def parse_cert(cert: str) -> str:
    """Parse a certificate and return its serial number."""
    try:
        cert = "\n".join(line.strip() for line in cert.strip().split("\n"))
        parsed = x509.load_pem_x509_certificate(cert.encode())
        return f'{parsed.serial_number:x}'
    except Exception:
        logging.error("Error parsing certificate.")
        return ""

def extract_certs(file_path: str) -> list:
    """Extract certificates from Keybox files (only .xml files)."""
    try:
        tree = etree.parse(file_path)
        root = tree.getroot()
        return [elem.text for elem in root.iter() if elem.tag == 'Certificate']
    except etree.XMLSyntaxError:
        logging.warning(f"{BOLD}{os.path.basename(file_path)} could not be parsed as XML.")
        return []

def keybox_check(file_content: bytes) -> bool:
    """Check if the keybox file content is valid based on CRL."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as tmp_file:
        tmp_file.write(file_content)
        tmp_file_path = tmp_file.name

    certs = extract_certs(tmp_file_path)
    os.unlink(tmp_file_path)  # Remove temp file

    if len(certs) < 4:
        return False

    ec_cert_sn = parse_cert(certs[0])
    rsa_cert_sn = parse_cert(certs[3])

    if not ec_cert_sn or not rsa_cert_sn:
        return False

    if ec_cert_sn in crl.get("entries", []) or rsa_cert_sn in crl.get("entries", []):
        return False

    return True

# Hàm lấy và xử lý kết quả tìm kiếm
def fetch_and_process_results(search_url: str, page: int) -> bool:
    global total_keybox_count
    params = {"per_page": 100, "page": page}
    # Lấy token tiếp theo trong vòng lặp
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
            # Chỉ xử lý các file XML
            if file_name.lower().endswith(".xml"):
                raw_url: str = (
                    item["html_url"].replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
                )
                # Kiểm tra xem file đã có trong cache chưa
                if raw_url + "\n" in cached_urls:
                    continue
                else:
                    cached_urls.add(raw_url + "\n")
                # Lấy nội dung file
                file_content = fetch_file_content(raw_url)
                # Phân tích XML
                try:
                    root = etree.fromstring(file_content)
                except etree.XMLSyntaxError:
                    continue
                # Lấy dạng chuẩn (C14N)
                canonical_xml = etree.tostring(root, method="c14n")
                # Băm nội dung XML
                hash_value = hashlib.sha256(canonical_xml).hexdigest()
                file_name_save = save / (hash_value + ".xml")
                if not file_name_save.exists() and file_content and keybox_check(file_content):
                    print(f"{raw_url} là file mới")
                    with open(file_name_save, "wb") as f:
                        f.write(file_content)
                    total_keybox_count += 1
                    keybox_urls[file_name_save] = raw_url
                    # Yêu cầu lưu file keybox hợp lệ
                    print(f"Đã lưu file keybox hợp lệ: {file_name_save.name}")
    return len(search_results["items"]) > 0  # Trả về True nếu có thể còn trang tiếp theo

# Hàm lấy nội dung file từ URL
def fetch_file_content(url: str) -> bytes:
    response = session.get(url)
    if response.status_code == 200:
        return response.content
    else:
        raise RuntimeError(f"Không thể tải file {url}")

# Xử lý tất cả các truy vấn tìm kiếm
for query in search_queries:
    print(f"Đang tìm kiếm với truy vấn: {query}")
    search_url = f"https://api.github.com/search/code?q={query}"
    page = 1
    while fetch_and_process_results(search_url, page):
        page += 1

# Cập nhật cache
open(cache_file, "w").writelines(cached_urls)

print(f"Tổng số keybox tìm thấy: {total_keybox_count}")

# In ra danh sách các file keybox hợp lệ (lưu riêng từng file)
print("\nLưu các file keybox hợp lệ riêng biệt:")
for file_path in save.glob("*.xml"):
    try:
        file_content = file_path.read_bytes()
        if keybox_check(file_content):
            # Lưu file keybox hợp lệ ra thư mục valid_keyboxes
            valid_dir = save.parent / "valid_keyboxes"
            valid_dir.mkdir(exist_ok=True)
            valid_file_path = valid_dir / file_path.name
            with open(valid_file_path, "wb") as vf:
                vf.write(file_content)
            print(f"Đã lưu keybox hợp lệ: {valid_file_path}")
    except Exception as e:
        print(f"Lỗi khi kiểm tra file {file_path.name}: {e}")
