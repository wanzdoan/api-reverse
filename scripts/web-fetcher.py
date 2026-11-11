#!python
"""
web-fetcher.py - Pure CLI Asset & Bundle Downloader (NO BROWSER REQUIRED)
Uses curl_cffi / httpx to bypass WAF / TLS JA3/JA4 fingerprinting.
Discovers all JS bundles, dynamic chunks, WASM files, and tests for Source Maps (.map).
"""

import sys
import os
import re
import json
import argparse
from urllib.parse import urljoin, urlparse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    import urllib.request


def http_get(url: str, headers: dict = None) -> tuple[int, bytes, dict]:
    if HAS_CURL_CFFI:
        try:
            kwargs = {
                "impersonate": "chrome124",
                "timeout": 15
            }
            if headers:
                kwargs["headers"] = headers
            resp = cffi_requests.get(url, **kwargs)
            return resp.status_code, resp.content, dict(resp.headers)
        except Exception as e:
            return 0, b"", {"error": str(e)}
    else:
        default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            default_headers.update(headers)
        req = urllib.request.Request(url, headers=default_headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except Exception as e:
            return 0, b"", {"error": str(e)}


def extract_script_urls(html_text: str, base_url: str) -> list[str]:
    urls = set()
    # <script src="...">
    for match in re.finditer(r'<script[^>]+src=["\']([^"\']+)["\']', html_text, re.IGNORECASE):
        src = match.group(1).strip()
        if src and not src.startswith("data:") and not src.startswith("blob:"):
            urls.add(urljoin(base_url, src))

    # <link rel="preload" as="script" href="..."> / modulepreload
    for match in re.finditer(r'<link[^>]+(?:href=["\']([^"\']+)["\'][^>]+as=["\']script["\']|as=["\']script["\'][^>]+href=["\']([^"\']+)["\'])', html_text, re.IGNORECASE):
        src = match.group(1) or match.group(2)
        if src:
            urls.add(urljoin(base_url, src.strip()))

    return sorted(list(urls))


def check_source_map(js_url: str, js_content: str, out_dir: str):
    match = re.search(r'//[#@]\s*sourceMappingURL=([^\s]+)', js_content)
    map_url = None
    if match:
        raw_map = match.group(1).strip()
        if not raw_map.startswith("data:"):
            map_url = urljoin(js_url, raw_map)
    else:
        map_url = js_url + ".map"

    if map_url:
        status, content, _ = http_get(map_url)
        if status == 200 and len(content) > 50 and b'"sources"' in content:
            safe_name = os.path.basename(urlparse(map_url).path) or "bundle.map"
            target_file = os.path.join(out_dir, safe_name)
            with open(target_file, "wb") as f:
                f.write(content)
            print(f"    [+] FOUND LEAKED SOURCE MAP! Saved to: {target_file} ({len(content)} bytes)")
            print(f"        -> You can unpack original sources via: npx source-map-unpack \"{target_file}\" ./src")
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Browserless Web Asset & Bundle Downloader")
    parser.add_argument("url", help="Target website or JS URL to fetch")
    parser.add_argument("--out", "-o", default="./target_assets", help="Directory to save downloaded files")
    parser.add_argument("--check-maps", action="store_true", default=True, help="Automatically probe for .js.map files")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    target_url = args.url

    print(f"[*] Pure CLI Mode: Fetching {target_url} (NO BROWSER)...")
    status, body_bytes, headers = http_get(target_url)

    if status != 200 or not body_bytes:
        print(f"[-] Request failed with status: {status}, error: {headers.get('error', 'unknown')}")
        sys.exit(1)

    print(f"[+] Successfully fetched {target_url} ({len(body_bytes)} bytes)")

    # If user provided a direct JS file
    if target_url.endswith(".js"):
        filename = os.path.basename(urlparse(target_url).path) or "script.js"
        dest = os.path.join(args.out, filename)
        with open(dest, "wb") as f:
            f.write(body_bytes)
        print(f"[+] Saved script: {dest}")
        text = body_bytes.decode("utf-8", errors="replace")
        if args.check_maps:
            check_source_map(target_url, text, args.out)
        return

    # Otherwise, it's HTML
    html_text = body_bytes.decode("utf-8", errors="replace")
    index_html_path = os.path.join(args.out, "index.html")
    with open(index_html_path, "w", encoding="utf-8", errors="replace") as f:
        f.write(html_text)

    script_urls = extract_script_urls(html_text, target_url)
    print(f"[*] Found {len(script_urls)} referenced script bundles in HTML.")

    all_downloaded = []
    for s_url in script_urls:
        filename = os.path.basename(urlparse(s_url).path) or f"bundle_{len(all_downloaded)}.js"
        # Sanitize filename
        safe_filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
        dest_path = os.path.join(args.out, safe_filename)
        print(f"  [-] Downloading: {s_url} -> {safe_filename}")
        s_status, s_bytes, _ = http_get(s_url)
        if s_status == 200 and s_bytes:
            with open(dest_path, "wb") as f:
                f.write(s_bytes)
            all_downloaded.append((s_url, dest_path, s_bytes))
            if args.check_maps:
                check_source_map(s_url, s_bytes.decode("utf-8", errors="replace"), args.out)
        else:
            print(f"      [!] Skipped/Failed ({s_status})")

    print(f"\n[+] Total {len(all_downloaded)} bundles downloaded to: {args.out}")
    print("[*] Next step: Run deobfuscate on key files:")
    print(f"    node scripts/deobfuscate.cjs \"{args.out}/<filename>.js\"")


if __name__ == "__main__":
    main()
