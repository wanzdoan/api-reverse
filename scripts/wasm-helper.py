#!python
"""
wasm-helper.py - WebAssembly (WASM) inspection, export/import extraction, and Ghidra integration.
No external dependencies required (pure standard Python).
"""

import sys
import os
import struct
import argparse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SECTION_NAMES = {
    0: "Custom",
    1: "Type",
    2: "Import",
    3: "Function",
    4: "Table",
    5: "Memory",
    6: "Global",
    7: "Export",
    8: "Start",
    9: "Element",
    10: "Code",
    11: "Data",
    12: "DataCount"
}


def read_leb128_u(data: bytes, offset: int):
    result = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7f) << shift
        if (byte & 0x80) == 0:
            break
        shift += 7
    return result, offset


def read_string(data: bytes, offset: int):
    length, offset = read_leb128_u(data, offset)
    s = data[offset:offset + length].decode("utf-8", errors="replace")
    return s, offset + length


def parse_wasm_headers(data: bytes):
    if len(data) < 8:
        raise ValueError("File is too short to be a valid WASM binary.")
    magic = data[:4]
    version = struct.unpack("<I", data[4:8])[0]
    if magic != b"\x00asm":
        raise ValueError(f"Invalid WASM magic header: {magic!r}")
    return version


def inspect_wasm(filepath: str):
    print(f"[*] Inspecting WebAssembly file: {filepath}")
    with open(filepath, "rb") as f:
        data = f.read()

    try:
        version = parse_wasm_headers(data)
    except Exception as e:
        print(f"[-] Error: {e}")
        return

    print(f"[+] Valid WebAssembly binary detected! Format version: {version}")
    print(f"    File size: {len(data)} bytes ({len(data) / 1024:.2f} KB)")

    offset = 8
    imports = []
    exports = []
    strings = []

    while offset < len(data):
        sec_id = data[offset]
        offset += 1
        sec_size, offset = read_leb128_u(data, offset)
        sec_end = offset + sec_size
        sec_name = SECTION_NAMES.get(sec_id, f"Unknown ({sec_id})")

        print(f"\n--- Section {sec_id}: {sec_name} ({sec_size} bytes) ---")

        if sec_id == 2:  # Import
            try:
                count, cur = read_leb128_u(data, offset)
                print(f"    Total imports: {count}")
                for _ in range(count):
                    if cur >= sec_end:
                        break
                    mod_name, cur = read_string(data, cur)
                    field_name, cur = read_string(data, cur)
                    import_kind = data[cur]
                    cur += 1
                    kind_desc = {0: "Func", 1: "Table", 2: "Mem", 3: "Global"}.get(import_kind, str(import_kind))
                    # read type idx / limits
                    _, cur = read_leb128_u(data, cur)
                    imports.append(f"{mod_name}.{field_name} ({kind_desc})")
                    print(f"      [Import] {mod_name}.{field_name} [{kind_desc}]")
            except Exception as ex:
                print(f"      [!] Failed parsing imports: {ex}")

        elif sec_id == 7:  # Export
            try:
                count, cur = read_leb128_u(data, offset)
                print(f"    Total exports: {count}")
                for _ in range(count):
                    if cur >= sec_end:
                        break
                    field_name, cur = read_string(data, cur)
                    export_kind = data[cur]
                    cur += 1
                    kind_desc = {0: "Func", 1: "Table", 2: "Mem", 3: "Global"}.get(export_kind, str(export_kind))
                    func_idx, cur = read_leb128_u(data, cur)
                    exports.append(f"{field_name} (idx {func_idx}, {kind_desc})")
                    print(f"      [Export] {field_name} -> index {func_idx} [{kind_desc}]")
            except Exception as ex:
                print(f"      [!] Failed parsing exports: {ex}")

        elif sec_id == 11:  # Data
            # Extract printable ASCII strings inside data section
            data_sec = data[offset:sec_end]
            curr_str = []
            for b in data_sec:
                if 32 <= b <= 126:
                    curr_str.append(chr(b))
                else:
                    if len(curr_str) >= 4:
                        s = "".join(curr_str)
                        strings.append(s)
                    curr_str = []
            if len(curr_str) >= 4:
                strings.append("".join(curr_str))

        offset = sec_end

    if strings:
        print(f"\n[+] Extracted Printable Strings from Data Segments ({len(strings)} strings):")
        for s in strings[:30]:
            print(f"    \"{s}\"")
        if len(strings) > 30:
            print(f"    ... and {len(strings) - 30} more strings.")

    print("\n" + "=" * 60)
    print(" Ghidra Headless Decompilation Guide:")
    print("=" * 60)
    ghidra_bat = r"D:\Tools\ghidra\support\analyzeHeadless.bat"
    if os.path.exists(ghidra_bat):
        print(f"Ghidra is available at: {ghidra_bat}")
        print("To decompile this WASM binary to C pseudocode:")
        print(f"  {ghidra_bat} <project_dir> wasm_proj -import \"{os.path.abspath(filepath)}\" -deleteProject")
    else:
        print("Install Ghidra or WABT (wasm2wat) to inspect control flow and assembly.")


def main():
    parser = argparse.ArgumentParser(description="WASM Inspector and Decompilation Helper")
    parser.add_argument("wasm_file", help="Path to .wasm file")
    args = parser.parse_args()

    if not os.path.exists(args.wasm_file):
        print(f"[-] File not found: {args.wasm_file}")
        sys.exit(1)

    inspect_wasm(args.wasm_file)


if __name__ == "__main__":
    main()
