# -*- coding: utf-8 -*-
# @Time: 2024/7/28 19:55
# @FileName: event.py
# @Software: PyCharm
# @GitHub: KimmyXYC

# Yep, completely stolen from @KimmyXYC. give them some love !

import re
import time
from datetime import datetime, timezone
from pathlib import Path
import shutil

import lxml.etree as ET
import requests
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding

url = "https://android.googleapis.com/attestation/status"
headers = {
    "Cache-Control": "max-age=0, no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

params = {"ts": int(time.time())}

response = requests.get(url, headers=headers, params=params)
if response.status_code != 200:
    raise Exception(f"Error fetching data: {response.reason}")
status_json = response.json()


def parse_number_of_certificates(xml_string):
    root = ET.fromstring(xml_string)
    number_of_certificates = root.find(".//NumberOfCertificates")
    if number_of_certificates is not None and number_of_certificates.text is not None:
        return int(number_of_certificates.text.strip())
    raise Exception("No NumberOfCertificates found.")


def parse_certificates(xml_string, pem_number):
    root = ET.fromstring(xml_string)
    pem_certificates = root.findall('.//Certificate[@format="pem"]')
    if pem_certificates is not None:
        return [cert.text.strip() if cert.text is not None else '' for cert in pem_certificates[:pem_number]]
    raise Exception("No Certificate found.")


def parse_private_key(xml_string):
    root = ET.fromstring(xml_string)
    private_key = root.find(".//PrivateKey")
    if private_key is not None and private_key.text is not None:
        return private_key.text.strip()
    raise Exception("No PrivateKey found.")


def load_public_key_from_file(file_path):
    with open(file_path, "rb") as key_file:
        return serialization.load_pem_public_key(key_file.read(), backend=default_backend())


def compare_keys(public_key1, public_key2):
    return public_key1.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    ) == public_key2.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )


def keybox_check(certificate_text):
    try:
        pem_number = parse_number_of_certificates(certificate_text)
        pem_certificates = parse_certificates(certificate_text, pem_number)
        private_key = parse_private_key(certificate_text)
    except Exception as e:
        print(f"[Keybox Check Error]: {e}")
        return False

    try:
        certificate = x509.load_pem_x509_certificate(pem_certificates[0].encode(), default_backend())
        try:
            private_key = re.sub(re.compile(r"^\s+", re.MULTILINE), "", private_key)
            private_key = serialization.load_pem_private_key(
                private_key.encode(), password=None, backend=default_backend()
            )
            check_private_key = True
        except Exception:
            check_private_key = False
    except Exception as e:
        print(f"[Keybox Check Error]: {e}")
        return False

    # Certificate validity
    current_time = datetime.now(timezone.utc)
    if not (certificate.not_valid_before_utc <= current_time <= certificate.not_valid_after_utc):
        return False

    # Check private key matches certificate
    if check_private_key:
        if not compare_keys(private_key.public_key(), certificate.public_key()):
            return False
    else:
        return False

    # Chain check
    for i in range(pem_number - 1):
        son = x509.load_pem_x509_certificate(pem_certificates[i].encode(), default_backend())
        father = x509.load_pem_x509_certificate(pem_certificates[i + 1].encode(), default_backend())
        if son.issuer != father.subject:
            return False
        try:
            sig_algo = son.signature_algorithm_oid._name
            if sig_algo.startswith("sha") and "RSA" in sig_algo:
                algo = {
                    "sha256WithRSAEncryption": hashes.SHA256(),
                    "sha1WithRSAEncryption": hashes.SHA1(),
                    "sha384WithRSAEncryption": hashes.SHA384(),
                    "sha512WithRSAEncryption": hashes.SHA512(),
                }[sig_algo]
                father.public_key().verify(son.signature, son.tbs_certificate_bytes, padding.PKCS1v15(), algo)
            elif sig_algo.startswith("ecdsa-with-"):
                algo = {
                    "ecdsa-with-SHA256": hashes.SHA256(),
                    "ecdsa-with-SHA1": hashes.SHA1(),
                    "ecdsa-with-SHA384": hashes.SHA384(),
                    "ecdsa-with-SHA512": hashes.SHA512(),
                }[sig_algo]
                father.public_key().verify(son.signature, son.tbs_certificate_bytes, ec.ECDSA(algo))
            else:
                return False
        except Exception:
            return False

    # Root check
    root_cert = x509.load_pem_x509_certificate(pem_certificates[-1].encode(), default_backend())
    root_key = root_cert.public_key()
    google = load_public_key_from_file("pem/google.pem")
    aosp_ec = load_public_key_from_file("pem/aosp_ec.pem")
    aosp_rsa = load_public_key_from_file("pem/aosp_rsa.pem")
    knox = load_public_key_from_file("pem/knox.pem")
    if compare_keys(root_key, google):
        pass
    elif compare_keys(root_key, aosp_ec) or compare_keys(root_key, aosp_rsa):
        return False
    elif compare_keys(root_key, knox):
        print("Found a knox key !?")
    else:
        return False

    # Max 3 certs
    if pem_number >= 4:
        return False

    # CRL check
    for i in range(pem_number):
        cert = x509.load_pem_x509_certificate(pem_certificates[i].encode(), default_backend())
        if status_json["entries"].get(hex(cert.serial_number)[2:].lower()):
            return False

    return True


# === ĐOẠN CHẠY THỰC TẾ: CHECK folder found_keybox ===

found_dir = Path("found_keybox")
valid_dir = Path("valid_keyboxes")
valid_dir.mkdir(exist_ok=True)

checked = 0
valid = 0

for xml_file in found_dir.glob("*.xml"):
    try:
        content = xml_file.read_text(encoding='utf-8')
        checked += 1
        if keybox_check(content):
            print(f"✅ {xml_file.name} hợp lệ → copied.")
            shutil.copy2(xml_file, valid_dir / xml_file.name)
            valid += 1
        else:
            print(f"❌ {xml_file.name} không hợp lệ.")
    except Exception as e:
        print(f"[Lỗi khi đọc {xml_file.name}]: {e}")

print(f"\nTổng cộng đã kiểm: {checked}, hợp lệ: {valid}")
