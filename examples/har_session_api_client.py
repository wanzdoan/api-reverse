#!/usr/bin/env python3
"""
har_session_api_client.py - Reference Template: API Client Reusing HAR Session & Probing APIs.
Demonstrates:
1. Reusing live cookies and auth headers extracted from a .har file.
2. Invoking discovered APIs with TLS JA3/JA4 impersonation via curl_cffi.
3. Automatically probing related endpoints to discover hidden functionality without a browser.
"""

import json
from curl_cffi import requests

class DemoApiClient:
    BASE_URL = "https://api.example.com"

    def __init__(self):
        self.session = requests.Session()
        
        # 1. Cookies extracted directly from the .har capture
        self.cookies = {
            "session_token": "live_session_cookie_from_har",
            "cf_clearance": "live_cloudflare_token_from_har",
            "user_id": "987654"
        }
        for k, v in self.cookies.items():
            self.session.cookies.set(k, v)

        # 2. Authorization and security headers from the .har capture
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Authorization": "Bearer eyJhbGciOi...",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9"
        }

    def get_profile(self):
        """Calls the main profile endpoint captured in the HAR."""
        url = f"{self.BASE_URL}/api/v1/user/profile"
        print(f"[*] Calling captured endpoint: {url}")
        resp = self.session.get(url, headers=self.headers, impersonate="chrome124", timeout=10)
        return resp

    def probe_related(self, candidate_paths: list[str]):
        """Probes adjacent or hidden endpoints using the active session."""
        print(f"\n[*] Probing {len(candidate_paths)} candidate endpoints using active HAR session...")
        discovered = []
        for path in candidate_paths:
            url = f"{self.BASE_URL}{path}"
            try:
                resp = self.session.get(url, headers=self.headers, impersonate="chrome124", timeout=10)
                if resp.status_code == 200:
                    print(f"  [+] SUCCESS [200 OK] -> {path}")
                    discovered.append((path, resp.status_code))
                elif resp.status_code == 403:
                    print(f"  [-] Forbidden [403]  -> {path}")
                elif resp.status_code == 404:
                    print(f"  [-] Not Found [404]  -> {path}")
                else:
                    print(f"  [?] Status [{resp.status_code}]   -> {path}")
            except Exception as e:
                print(f"  [!] Failed {path}: {e}")
        return discovered


def main():
    client = DemoApiClient()
    print("[*] Initialized DemoApiClient with session credentials.")
    
    # 1. Probing related endpoints based on the base pattern /api/v1/user/...
    candidates = [
        "/api/v1/user/settings",
        "/api/v1/user/wallets",
        "/api/v1/user/notifications",
        "/api/v1/user/security",
        "/api/v1/orders/history"
    ]
    # client.probe_related(candidates)

if __name__ == "__main__":
    main()
