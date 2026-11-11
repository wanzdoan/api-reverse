#!python
"""
curl-to-code.py - Convert cURL command or HAR entry into parameterized Python / Node.js replay script.
Supports curl_cffi for TLS JA3/JA4 fingerprint impersonation.
"""

import sys
import re
import json
import shlex
import argparse
from urllib.parse import urlparse, parse_qs

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def parse_curl(curl_command: str):
    # Normalize command
    curl_command = curl_command.replace("\\\n", " ").replace("^\n", " ").strip()
    
    # Split using shlex (handle Windows & POSIX quoting)
    try:
        tokens = shlex.split(curl_command, posix=False)
    except Exception:
        tokens = curl_command.split()

    url = ""
    method = "GET"
    headers = {}
    data = None
    compressed = False

    i = 0
    while i < len(tokens):
        token = tokens[i].strip("'\"")
        
        if token in ("curl", "curl.exe"):
            i += 1
            continue
            
        if token.startswith("http://") or token.startswith("https://"):
            url = token
            i += 1
            continue
            
        if token in ("-X", "--request") and i + 1 < len(tokens):
            method = tokens[i + 1].strip("'\"").upper()
            i += 2
            continue
            
        if token in ("-H", "--header") and i + 1 < len(tokens):
            header_line = tokens[i + 1].strip("'\"")
            if ":" in header_line:
                k, v = header_line.split(":", 1)
                headers[k.strip()] = v.strip()
            i += 2
            continue
            
        if token in ("-d", "--data", "--data-raw", "--data-binary") and i + 1 < len(tokens):
            data = tokens[i + 1].strip("'\"")
            if method == "GET":
                method = "POST"
            i += 2
            continue
            
        if token in ("-b", "--cookie") and i + 1 < len(tokens):
            headers["Cookie"] = tokens[i + 1].strip("'\"")
            i += 2
            continue
            
        if token == "--compressed":
            compressed = True
            i += 1
            continue
            
        # If url wasn't matched yet and doesn't start with -
        if not url and not token.startswith("-") and ("." in token or "/" in token):
            url = token

        i += 1

    return {
        "url": url,
        "method": method,
        "headers": headers,
        "data": data,
        "compressed": compressed
    }


def generate_python_curl_cffi(parsed: dict) -> str:
    url = parsed["url"]
    method = parsed["method"]
    headers = parsed["headers"]
    data = parsed["data"]

    # Filter out pseudo-headers or headers curl_cffi handles
    clean_headers = {k: v for k, v in headers.items() if not k.startswith(":") and k.lower() not in ("content-length",)}

    lines = []
    lines.append('import json')
    lines.append('import time')
    lines.append('# pip install curl_cffi (provides JA3/JA4 TLS browser fingerprint impersonation)')
    lines.append('from curl_cffi import requests')
    lines.append('')
    lines.append('def main():')
    lines.append(f'    url = {repr(url)}')
    lines.append('')
    
    # Headers
    lines.append('    headers = {')
    for k, v in clean_headers.items():
        # Highlight potential signatures
        comment = ""
        if any(sig in k.lower() for sig in ['sign', 'token', 'auth', 'nonce', 'timestamp']):
            comment = "  # <-- DYNAMIC / SECURITY HEADER"
        lines.append(f'        {repr(k)}: {repr(v)},{comment}')
    lines.append('    }')
    lines.append('')

    # Body
    if data:
        try:
            parsed_json = json.loads(data)
            lines.append('    # JSON Payload')
            lines.append('    payload = {')
            for pk, pv in parsed_json.items():
                comment = ""
                if any(sig in pk.lower() for sig in ['sign', 'token', 't', 'nonce']):
                    comment = "  # <-- DYNAMIC / SIGNATURE FIELD"
                lines.append(f'        {repr(pk)}: {repr(pv)},{comment}')
            lines.append('    }')
            lines.append(f'    response = requests.{method.lower()}(')
            lines.append('        url,')
            lines.append('        headers=headers,')
            lines.append('        json=payload,')
            lines.append('        impersonate="chrome124",  # Emulates Chrome TLS fingerprint')
            lines.append('        timeout=15')
            lines.append('    )')
        except Exception:
            lines.append(f'    data = {repr(data)}')
            lines.append(f'    response = requests.{method.lower()}(')
            lines.append('        url,')
            lines.append('        headers=headers,')
            lines.append('        data=data,')
            lines.append('        impersonate="chrome124",')
            lines.append('        timeout=15')
            lines.append('    )')
    else:
        lines.append(f'    response = requests.{method.lower()}(')
        lines.append('        url,')
        lines.append('        headers=headers,')
        lines.append('        impersonate="chrome124",')
        lines.append('        timeout=15')
        lines.append('    )')

    lines.append('')
    lines.append('    print(f"Status Code: {response.status_code}")')
    lines.append('    print("Response Headers:", response.headers)')
    lines.append('    try:')
    lines.append('        print("JSON Response:", json.dumps(response.json(), indent=2, ensure_ascii=False))')
    lines.append('    except Exception:')
    lines.append('        print("Text Response (first 500 chars):", response.text[:500])')
    lines.append('')
    lines.append('if __name__ == "__main__":')
    lines.append('    main()')

    return "\n".join(lines)


def generate_node_fetch(parsed: dict) -> str:
    url = parsed["url"]
    method = parsed["method"]
    headers = parsed["headers"]
    data = parsed["data"]

    clean_headers = {k: v for k, v in headers.items() if not k.startswith(":")}

    lines = []
    lines.append('// Replay script using Node.js native fetch (Node 18+)')
    lines.append('async function run() {')
    lines.append(f'  const url = {json.dumps(url)};')
    lines.append('  const headers = {')
    for k, v in clean_headers.items():
        comment = ""
        if any(sig in k.lower() for sig in ['sign', 'token', 'auth']):
            comment = " // <-- Dynamic Header"
        lines.append(f'    {json.dumps(k)}: {json.dumps(v)},{comment}')
    lines.append('  };')
    lines.append('')
    
    lines.append('  const options = {')
    lines.append(f'    method: {json.dumps(method)},')
    lines.append('    headers: headers,')
    if data:
        lines.append(f'    body: {json.dumps(data)},')
    lines.append('  };')
    lines.append('')
    lines.append('  console.log(`[*] Sending ${options.method} request to ${url}...`);')
    lines.append('  const res = await fetch(url, options);')
    lines.append('  console.log(`[+] Status: ${res.status}`);')
    lines.append('  const text = await res.text();')
    lines.append('  try {')
    lines.append('    console.log("JSON:", JSON.parse(text));')
    lines.append('  } catch (_) {')
    lines.append('    console.log("Text:", text.slice(0, 500));')
    lines.append('  }')
    lines.append('}')
    lines.append('')
    lines.append('run();')

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Convert cURL to Python (curl_cffi / httpx) or Node.js fetch")
    parser.add_argument("curl_file_or_string", nargs="?", default="", help="cURL command string or file containing cURL")
    parser.add_argument("--lang", choices=["python", "node"], default="python", help="Output programming language")
    parser.add_argument("--out", "-o", help="Save generated code to file")

    args = parser.parse_args()

    content = args.curl_file_or_string
    if not content:
        if not sys.stdin.isatty():
            content = sys.stdin.read()
        else:
            parser.print_help()
            sys.exit(0)

    parsed = parse_curl(content)
    if not parsed["url"]:
        print("[-] Error: Unable to parse URL from cURL command.")
        sys.exit(1)

    if args.lang == "python":
        code = generate_python_curl_cffi(parsed)
    else:
        code = generate_node_fetch(parsed)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"[+] Replay script written to: {args.out}")
    else:
        print(code)


if __name__ == "__main__":
    main()
