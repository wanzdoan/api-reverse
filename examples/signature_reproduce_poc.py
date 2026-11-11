#!/usr/bin/env python3
"""
signature_reproduce_poc.py - Reference Template for Web API Request Signing & Replay.
Demonstrates:
1. Dynamic Timestamp & Nonce Generation
2. Parameter Canonicalization (Alphabetical Sorting)
3. Cryptographic Signature Emulation (HMAC-SHA256 / MD5)
4. Full Request Replay using curl_cffi for TLS JA3/JA4 Fingerprint Spoofing
"""

import time
import uuid
import hmac
import hashlib
import json
from curl_cffi import requests

# Reconstructed parameters from reverse engineering
API_BASE_URL = "https://api.target.com"
ENDPOINT_PATH = "/v1/secure/data"
API_SECRET_KEY = "k3y_s3cr3t_d1sc0v3r3d_fr0m_js"


def calculate_signature(method: str, path: str, timestamp: int, nonce: str, payload_dict: dict) -> str:
    """
    Reconstructed signature algorithm:
    sign = HMAC_SHA256(
        secret_key,
        METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + NONCE + "\n" + SORTED_JSON_STRING
    )
    """
    # 1. Canonicalize payload: Sort keys alphabetically, compact JSON without extra whitespace
    canonical_body = json.dumps(payload_dict, sort_keys=True, separators=(',', ':'))
    
    # 2. Build string to sign
    sign_payload = f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{canonical_body}"
    
    # 3. Compute HMAC-SHA256
    sig = hmac.new(
        API_SECRET_KEY.encode('utf-8'),
        sign_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return sig


def fetch_secure_data(query_query: str):
    timestamp = int(time.time() * 1000)
    nonce = uuid.uuid4().hex[:16]
    
    payload = {
        "query": query_query,
        "page": 1,
        "pageSize": 20
    }
    
    signature = calculate_signature("POST", ENDPOINT_PATH, timestamp, nonce, payload)
    
    headers = {
        "Content-Type": "application/json",
        "X-Timestamp": str(timestamp),
        "X-Nonce": nonce,
        "X-Signature": signature,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    
    target_url = f"{API_BASE_URL}{ENDPOINT_PATH}"
    print(f"[*] Dispatching request to: {target_url}")
    print(f"[*] Generated Signature: {signature}")
    
    # Use curl_cffi to match browser TLS JA3/JA4 fingerprint
    response = requests.post(
        target_url,
        headers=headers,
        json=payload,
        impersonate="chrome124",
        timeout=10
    )
    
    print(f"[+] HTTP Status: {response.status_code}")
    try:
        print("[+] JSON Data:", json.dumps(response.json(), indent=2, ensure_ascii=False))
    except Exception:
        print("[+] Raw Response:", response.text[:500])


if __name__ == "__main__":
    # Test execution
    fetch_secure_data("sample_keyword")
