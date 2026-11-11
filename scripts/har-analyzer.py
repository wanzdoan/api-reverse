#!python
"""
har-analyzer.py - Pure CLI HAR & Network Dump Analyzer (NO BROWSER)
Capabilities:
1. Parse and filter API requests/responses from .har or JSON dump.
2. Extract live session state (Cookies, Auth tokens, Headers, User-Agent) -> JSON or Python.
3. Automatically generate a modular Python API Client (curl_cffi) using the extracted cookies/headers.
4. Discover related API endpoints from response bodies and JavaScript files inside the HAR.
5. Diff requests to spot dynamic signature fields.
"""

import sys
import os
import re
import json
import argparse
from urllib.parse import urlparse, parse_qs, urljoin

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_har(har_path: str) -> list[dict]:
    with open(har_path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    if "log" in data and "entries" in data["log"]:
        return data["log"]["entries"]
    elif isinstance(data, list):
        return data
    return []


def analyze_security_headers(headers: list[dict] | dict) -> list[tuple[str, str]]:
    h_dict = {}
    if isinstance(headers, list):
        for h in headers:
            h_dict[h.get("name", "")] = h.get("value", "")
    elif isinstance(headers, dict):
        h_dict = headers

    findings = []
    keywords = ["sign", "token", "auth", "secret", "timestamp", "nonce", "digest", "key", "sec-"]
    for k, v in h_dict.items():
        k_lower = k.lower()
        if any(kw in k_lower for kw in keywords):
            findings.append((k, v))
    return findings


def extract_session_state(entries: list[dict]) -> dict:
    """Extract aggregated cookies, authorization headers, and common browser headers."""
    cookies = {}
    auth_headers = {}
    user_agents = set()
    base_urls = set()
    common_headers = {}

    for entry in entries:
        req = entry.get("request", entry)
        url = req.get("url", "")
        if url:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                base_urls.add(f"{parsed.scheme}://{parsed.netloc}")

        # Cookies from request
        req_cookies = req.get("cookies", [])
        for c in req_cookies:
            if "name" in c and "value" in c:
                cookies[c["name"]] = c["value"]

        # Parse Cookie header if present
        headers = req.get("headers", [])
        h_dict = {h["name"]: h["value"] for h in headers if "name" in h} if isinstance(headers, list) else (headers or {})

        if "Cookie" in h_dict:
            for part in h_dict["Cookie"].split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    cookies[k.strip()] = v.strip()
        elif "cookie" in h_dict:
            for part in h_dict["cookie"].split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    cookies[k.strip()] = v.strip()

        # Cookies from response Set-Cookie
        resp_headers = entry.get("response", {}).get("headers", [])
        if isinstance(resp_headers, list):
            for h in resp_headers:
                if h.get("name", "").lower() == "set-cookie":
                    cookie_str = h.get("value", "").split(";")[0]
                    if "=" in cookie_str:
                        ck, cv = cookie_str.split("=", 1)
                        cookies[ck.strip()] = cv.strip()

        # Auth & Security headers
        for k, v in h_dict.items():
            k_lower = k.lower()
            if k_lower in ("authorization", "x-token", "x-auth-token", "x-access-token", "x-csrf-token", "x-xsrf-token", "token"):
                auth_headers[k] = v
            elif k_lower.startswith("x-") and ("sign" in k_lower or "auth" in k_lower or "sec" in k_lower):
                auth_headers[k] = v
            elif k_lower == "user-agent":
                user_agents.add(v)
            elif k_lower in ("accept", "accept-language", "origin", "referer"):
                common_headers[k] = v

    primary_ua = list(user_agents)[0] if user_agents else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    primary_base = list(base_urls)[0] if base_urls else ""

    return {
        "base_url": primary_base,
        "all_base_urls": list(base_urls),
        "user_agent": primary_ua,
        "cookies": cookies,
        "auth_headers": auth_headers,
        "common_headers": common_headers
    }


def discover_hidden_endpoints(entries: list[dict]) -> set[str]:
    """Scans response bodies (JSON, HTML, JS) inside the HAR to find referenced API routes."""
    endpoints = set()
    endpoint_pattern = re.compile(r'["\'](/(?:api|v[0-9]+|rest|graphql|internal|user|auth|order|admin)/[a-zA-Z0-9_\-\./]+)["\']')

    for entry in entries:
        # Check URL itself
        req_url = entry.get("request", entry).get("url", "")
        if req_url:
            parsed = urlparse(req_url)
            if "/api/" in parsed.path or parsed.path.startswith("/v"):
                endpoints.add(parsed.path)

        # Check response content
        resp = entry.get("response", {})
        content = resp.get("content", {}).get("text", "")
        if content:
            matches = endpoint_pattern.findall(content)
            for m in matches:
                # Exclude static file extensions
                if not any(m.endswith(ext) for ext in [".png", ".jpg", ".css", ".svg", ".ico", ".woff"]):
                    endpoints.add(m)

    return endpoints


def generate_python_client(session_state: dict, entries: list[dict], out_path: str):
    """Generates a complete, modular Python API client using curl_cffi and the extracted cookies/headers."""
    base_url = session_state.get("base_url") or "https://api.target.com"
    cookies = session_state.get("cookies", {})
    auth_headers = session_state.get("auth_headers", {})
    user_agent = session_state.get("user_agent", "")

    # Group unique API endpoints from entries
    api_map = {}
    for e in entries:
        req = e.get("request", e)
        url = req.get("url", "")
        method = req.get("method", "GET").upper()
        if not url:
            continue
        parsed = urlparse(url)
        path = parsed.path
        if "/api/" in path or "/v1/" in path or "/v2/" in path or "graphql" in path:
            if path not in api_map:
                api_map[path] = {
                    "method": method,
                    "url": url,
                    "path": path,
                    "query_params": parse_qs(parsed.query),
                    "post_data": req.get("postData", {}).get("text", "")
                }

    lines = []
    lines.append('#!/usr/bin/env python3')
    lines.append('"""')
    lines.append('Auto-generated Browserless API Client from HAR capture.')
    lines.append('Uses curl_cffi with Chrome TLS JA3/JA4 fingerprint impersonation.')
    lines.append('Includes pre-extracted session cookies, auth headers, and probing utilities.')
    lines.append('"""')
    lines.append('')
    lines.append('import json')
    lines.append('import time')
    lines.append('from typing import Optional, Dict, Any')
    lines.append('from curl_cffi import requests')
    lines.append('')
    lines.append('')
    lines.append('class ApiClient:')
    lines.append(f'    BASE_URL = {repr(base_url)}')
    lines.append('')
    lines.append('    def __init__(self, impersonate: str = "chrome124"):')
    lines.append('        self.session = requests.Session()')
    lines.append('        self.impersonate = impersonate')
    lines.append('')
    lines.append('        # 1. Extracted Live Cookies from HAR')
    lines.append('        self.cookies = {')
    for ck, cv in cookies.items():
        lines.append(f'            {repr(ck)}: {repr(cv)},')
    lines.append('        }')
    lines.append('        for k, v in self.cookies.items():')
    lines.append('            self.session.cookies.set(k, v)')
    lines.append('')
    lines.append('        # 2. Extracted Security & Common Headers')
    lines.append('        self.headers = {')
    lines.append(f'            "User-Agent": {repr(user_agent)},')
    lines.append('            "Accept": "application/json, text/plain, */*",')
    lines.append('            "Accept-Language": "en-US,en;q=0.9",')
    for hk, hv in auth_headers.items():
        lines.append(f'            {repr(hk)}: {repr(hv)},  # Extracted Auth Token')
    lines.append('        }')
    lines.append('')
    lines.append('    def request(self, method: str, path_or_url: str, params: Optional[dict] = None, json_data: Optional[dict] = None, **kwargs) -> requests.Response:')
    lines.append('        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):')
    lines.append('            url = path_or_url')
    lines.append('        else:')
    lines.append('            url = self.BASE_URL.rstrip("/") + "/" + path_or_url.lstrip("/")')
    lines.append('')
    lines.append('        headers = kwargs.pop("headers", self.headers.copy())')
    lines.append('        print(f"[*] [{method.upper()}] Sending to: {url}")')
    lines.append('        resp = self.session.request(')
    lines.append('            method=method,')
    lines.append('            url=url,')
    lines.append('            headers=headers,')
    lines.append('            params=params,')
    lines.append('            json=json_data,')
    lines.append('            impersonate=self.impersonate,')
    lines.append('            timeout=15,')
    lines.append('            **kwargs')
    lines.append('        )')
    lines.append('        print(f"[+] Status: {resp.status_code}")')
    lines.append('        return resp')
    lines.append('')

    # Generate specific endpoint helpers from HAR
    lines.append('    # -------------------------------------------------------------')
    lines.append('    # Endpoints Discovered in HAR')
    lines.append('    # -------------------------------------------------------------')
    for idx, (path, info) in enumerate(list(api_map.items())[:15]):
        # Sanitize func name
        func_name = re.sub(r'[^a-zA-Z0-9_]', '_', path.strip('/')).lower()
        if not func_name:
            func_name = f"api_endpoint_{idx}"
        method = info["method"].lower()

        lines.append(f'    def {method}_{func_name}(self, **kwargs) -> Any:')
        lines.append(f'        """Captured from HAR: {info["method"]} {path}"""')
        lines.append(f'        resp = self.request({repr(method)}, {repr(path)}, **kwargs)')
        lines.append('        try:')
        lines.append('            return resp.json()')
        lines.append('        except Exception:')
        lines.append('            return resp.text')
        lines.append('')

    # Endpoint probing method
    lines.append('    # -------------------------------------------------------------')
    lines.append('    # API Probing Utility (Đục thêm các API liên quan)')
    lines.append('    # -------------------------------------------------------------')
    lines.append('    def probe_endpoint(self, candidate_path: str, method: str = "GET", params: Optional[dict] = None, json_data: Optional[dict] = None):')
    lines.append('        """Probe an uncaptured or related API endpoint using live session credentials."""')
    lines.append('        print(f"[*] Probing related endpoint: {candidate_path} ...")')
    lines.append('        try:')
    lines.append('            resp = self.request(method, candidate_path, params=params, json_data=json_data)')
    lines.append('            if resp.status_code == 200:')
    lines.append('                print(f"[+] PROBE SUCCESS [200 OK]: {candidate_path}")')
    lines.append('                try:')
    lines.append('                    print(json.dumps(resp.json(), indent=2, ensure_ascii=False)[:300] + "...\\n")')
    lines.append('                except Exception:')
    lines.append('                    print(resp.text[:200] + "\\n")')
    lines.append('                return True, resp')
    lines.append('            elif resp.status_code in (401, 403):')
    lines.append('                print(f"[-] Forbidden / Unauthorized [{resp.status_code}]: {candidate_path}")')
    lines.append('            elif resp.status_code == 404:')
    lines.append('                print(f"[-] Not Found [404]: {candidate_path}")')
    lines.append('            else:')
    lines.append('                print(f"[?] Response [{resp.status_code}]: {candidate_path}")')
    lines.append('            return False, resp')
    lines.append('        except Exception as e:')
    lines.append('            print(f"[!] Error probing {candidate_path}: {e}")')
    lines.append('            return False, None')
    lines.append('')

    # Main runner
    lines.append('def main():')
    lines.append('    client = ApiClient()')
    lines.append('    print("[*] ApiClient successfully initialized with HAR session state.")')
    lines.append('    print(f"[*] Loaded {len(client.cookies)} cookies and {len(client.headers)} headers.")')
    lines.append('    print("")')
    lines.append('    # Example test call (uncomment to test):')
    lines.append('    # res = client.request("GET", "/api/user/profile")')
    lines.append('    # print(res.text[:300])')
    lines.append('')
    lines.append('if __name__ == "__main__":')
    lines.append('    main()')

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[+] Generated standalone API Client script -> {out_path}")


def diff_requests(req1: dict, req2: dict):
    print("\n" + "=" * 60)
    print(" DIFFING TWO REQUESTS TO DETECT DYNAMIC PARAMS & SIGNATURES:")
    print("=" * 60)

    url1 = req1.get("request", {}).get("url") or req1.get("url", "")
    url2 = req2.get("request", {}).get("url") or req2.get("url", "")
    print(f"URL 1: {url1}")
    print(f"URL 2: {url2}")

    p1 = parse_qs(urlparse(url1).query)
    p2 = parse_qs(urlparse(url2).query)
    all_keys = set(p1.keys()).union(set(p2.keys()))

    print("\n[Query Parameters Comparison]:")
    for k in sorted(all_keys):
        v1 = p1.get(k, ["<MISSING>"])[0]
        v2 = p2.get(k, ["<MISSING>"])[0]
        status = "STATIC" if v1 == v2 else "**DYNAMIC** (Varies per request)"
        print(f"  {k:20}: {v1:30} vs {v2:30} [{status}]")

    def get_h_dict(r):
        hdrs = r.get("request", {}).get("headers") or r.get("headers", {})
        if isinstance(hdrs, list):
            return {h["name"]: h["value"] for h in hdrs if "name" in h}
        return hdrs

    h1 = get_h_dict(req1)
    h2 = get_h_dict(req2)
    all_h = set(h1.keys()).union(set(h2.keys()))

    print("\n[Headers Comparison]:")
    for hk in sorted(all_h):
        val1 = h1.get(hk, "<MISSING>")
        val2 = h2.get(hk, "<MISSING>")
        if val1 != val2:
            print(f"  [DYNAMIC HEADER] {hk:20}: {val1[:30]} vs {val2[:30]}")


def export_curl(entry: dict) -> str:
    req = entry.get("request", entry)
    url = req.get("url", "")
    method = req.get("method", "GET")
    headers = req.get("headers", [])
    post_data = req.get("postData", {}).get("text", "")

    lines = [f"curl -X {method} '{url}'"]
    if isinstance(headers, list):
        for h in headers:
            if not h["name"].startswith(":"):
                lines.append(f"  -H '{h['name']}: {h['value']}'")
    elif isinstance(headers, dict):
        for k, v in headers.items():
            if not k.startswith(":"):
                lines.append(f"  -H '{k}: {v}'")

    if post_data:
        escaped = post_data.replace("'", "'\\''")
        lines.append(f"  --data-raw '{escaped}'")

    return " \\\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="CLI HAR and Network Dump Security & Session Analyzer")
    parser.add_argument("har_file", help="Path to .har or JSON network capture file")
    parser.add_argument("--filter", "-f", default="", help="Filter requests by URL keyword (e.g. 'api')")
    parser.add_argument("--export-session", "-s", help="Save extracted live cookies & auth headers to JSON file")
    parser.add_argument("--gen-client", "-g", help="Generate complete Python API Client (curl_cffi) from HAR session")
    parser.add_argument("--find-endpoints", action="store_true", help="Discover related or hidden API endpoints in response bodies")
    parser.add_argument("--diff", action="store_true", help="Compare first two matching requests to spot dynamic parameters")
    parser.add_argument("--export-curl", action="store_true", help="Print matching requests as cURL commands")

    args = parser.parse_args()

    if not os.path.exists(args.har_file):
        print(f"[-] File not found: {args.har_file}")
        sys.exit(1)

    entries = load_har(args.har_file)
    print(f"[*] Loaded {len(entries)} entries from {args.har_file}")

    # Extract session state
    session_state = extract_session_state(entries)
    print(f"[+] Extracted Session State:")
    print(f"    Base URL    : {session_state['base_url']}")
    print(f"    Cookies     : {len(session_state['cookies'])} cookies found")
    for ck in list(session_state['cookies'].keys())[:5]:
        print(f"      - {ck}")
    if len(session_state['cookies']) > 5:
        print(f"      ... and {len(session_state['cookies']) - 5} more.")

    print(f"    Auth Headers: {len(session_state['auth_headers'])} items")
    for hk, hv in session_state['auth_headers'].items():
        print(f"      - {hk}: {hv[:40]}...")

    if args.export_session:
        with open(args.export_session, "w", encoding="utf-8") as f:
            json.dump(session_state, f, indent=2, ensure_ascii=False)
        print(f"[+] Saved session state -> {args.export_session}")

    if args.gen_client:
        generate_python_client(session_state, entries, args.gen_client)

    if args.find_endpoints:
        hidden = discover_hidden_endpoints(entries)
        print(f"\n[+] Discovered {len(hidden)} API Routes across HAR requests & responses:")
        for ep in sorted(list(hidden)):
            print(f"    - {ep}")

    # Filtered requests
    if args.filter or args.export_curl or args.diff:
        matched = []
        for idx, e in enumerate(entries):
            req = e.get("request", e)
            url = req.get("url", "")
            method = req.get("method", "GET")
            if not args.filter or args.filter.lower() in url.lower():
                matched.append((idx, e))

        print(f"\n[+] Found {len(matched)} matching requests with filter '{args.filter}':\n")
        for i, (idx, entry) in enumerate(matched[:20]):
            req = entry.get("request", entry)
            url = req.get("url", "")
            method = req.get("method", "GET")
            status = entry.get("response", {}).get("status", "N/A")
            print(f"[{i+1}] Index #{idx}: {method} ({status}) -> {url}")

            sec_headers = analyze_security_headers(req.get("headers", []))
            if sec_headers:
                print("    Security / Signature Headers:")
                for hk, hv in sec_headers:
                    print(f"      - {hk}: {hv}")

            if args.export_curl:
                print("\n    cURL command:")
                print(export_curl(entry) + "\n")

        if args.diff and len(matched) >= 2:
            diff_requests(matched[0][1], matched[1][1])


if __name__ == "__main__":
    main()
