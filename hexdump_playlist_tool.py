import argparse
import json
import os

from bbt_level_tool import build_level_bytes, parse_level_bytes


NAME_ENTRY_SIZE = 32


def load_hex_text(path):
    with open(path, "r", encoding="utf-8") as file_obj:
        tokens = file_obj.read().split()
    return bytes(int(token, 16) for token in tokens)


def decode_name_entry(chunk):
    if len(chunk) != NAME_ENTRY_SIZE:
        return None

    odd_bytes = chunk[1::2]
    if sum(1 for value in odd_bytes if value == 0) < 10:
        return None

    try:
        text = chunk.decode("utf-16le").rstrip("\x00").strip()
    except UnicodeDecodeError:
        return None

    if not text:
        return None

    return text


def parse_name_table(data):
    names = []
    offset = 0

    while offset + NAME_ENTRY_SIZE <= len(data):
        chunk = data[offset:offset + NAME_ENTRY_SIZE]
        text = decode_name_entry(chunk)
        if text is None:
            break
        names.append(text)
        offset += NAME_ENTRY_SIZE

    return names, offset


def parse_records(data, start_offset, level_names):
    offset = start_offset
    records = []
    raw_records = []

    for name in level_names:
        if offset + 5 > len(data):
            raise ValueError(f"Unexpected end of data while reading record header for {name}")

        size = int.from_bytes(data[offset:offset + 4], "little")
        flag = data[offset + 4]
        record_offset = offset
        offset += 5

        record_bytes = data[offset:offset + size]
        if len(record_bytes) != size:
            raise ValueError(f"Unexpected end of data while reading {name}: wanted {size} bytes")

        raw_records.append(
            {
                "name": name,
                "record_size": size,
                "record_flag": flag,
                "record_offset": record_offset,
                "record_bytes": record_bytes,
            }
        )
        offset += size

    trailer = data[offset:]
    return raw_records, trailer


def scan_level_records(data):
    matches = []
    seen = set()

    for offset in range(0, len(data) - 21):
        size = int.from_bytes(data[offset:offset + 4], "little")
        flag = data[offset + 4]

        if flag != 0:
            continue
        if size < 16 or size > 10000:
            continue
        end = offset + 5 + size
        if end > len(data):
            continue

        record_bytes = data[offset + 5:end]

        try:
            parsed = parse_level_bytes(record_bytes)
        except ValueError:
            continue

        key = (size, record_bytes[:16], record_bytes[-16:])
        if key in seen:
            continue
        seen.add(key)

        parsed["record_size"] = size
        parsed["record_flag"] = flag
        parsed["record_offset"] = offset
        matches.append(parsed)

    return matches


def export_hexdump(input_path, output_dir):
    data = load_hex_text(input_path)
    names, records_offset = parse_name_table(data)
    if len(names) < 2:
        raise ValueError("Could not parse playlist name and level names from dump")

    playlist_name = names[0]
    level_names = names[1:]
    raw_records, trailer = parse_records(data, records_offset, level_names)
    scanned_levels = scan_level_records(data)

    if len(scanned_levels) >= len(level_names):
        raw_records = []
        for index, name in enumerate(level_names):
            entry = scanned_levels[index]
            raw_records.append(
                {
                    "name": name,
                    "record_size": entry["record_size"],
                    "record_flag": entry["record_flag"],
                    "record_offset": entry["record_offset"],
                    "record_bytes": build_level_bytes(entry),
                }
            )
        trailer = b""

    os.makedirs(output_dir, exist_ok=True)

    manifest = {
        "source_hex_file": input_path,
        "playlist_name": playlist_name,
        "record_count": len(raw_records),
        "trailing_bytes_hex": trailer.hex().upper(),
        "entries": [],
    }

    exported_count = 0
    skipped_count = 0
    for index, raw_entry in enumerate(raw_records, start=1):
        try:
            entry = parse_level_bytes(raw_entry["record_bytes"])
        except ValueError:
            skipped_count += 1
            manifest["entries"].append(
                {
                    "index": index,
                    "name": raw_entry["name"],
                    "record_size": raw_entry["record_size"],
                    "record_flag": raw_entry["record_flag"],
                    "record_offset": raw_entry["record_offset"],
                    "kind": "raw",
                    "raw_hex": raw_entry["record_bytes"].hex().upper(),
                }
            )
            continue

        exported_count += 1
        entry["name"] = raw_entry["name"]
        entry["record_size"] = raw_entry["record_size"]
        entry["record_flag"] = raw_entry["record_flag"]
        entry["record_offset"] = raw_entry["record_offset"]

        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_", " ") else "_" for ch in entry["name"]).strip()
        safe_name = safe_name.replace(" ", "_")
        json_name = f"{index:02d}_{safe_name}.json"
        json_path = os.path.join(output_dir, json_name)

        with open(json_path, "w", encoding="utf-8") as file_obj:
            json.dump(entry, file_obj, indent=2)
            file_obj.write("\n")

        manifest["entries"].append(
            {
                "index": index,
                "name": entry["name"],
                "json_file": json_name,
                "record_size": entry["record_size"],
                "record_flag": entry["record_flag"],
                "record_offset": entry["record_offset"],
                "kind": "level",
            }
        )

    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as file_obj:
        json.dump(manifest, file_obj, indent=2)
        file_obj.write("\n")

    print(f"Playlist: {playlist_name}")
    print(f"Exported {exported_count} level entries to {output_dir}")
    print(f"Skipped {skipped_count} non-level/raw entries")
    print(f"Detected {len(scanned_levels)} embedded level blobs in total")
    print(f"Manifest: {manifest_path}")


def encode_name_entry(name):
    encoded = name.encode("utf-16le")
    if len(encoded) > NAME_ENTRY_SIZE:
        raise ValueError(f"Name is too long for fixed {NAME_ENTRY_SIZE}-byte entry: {name}")
    return encoded + (b"\x00" * (NAME_ENTRY_SIZE - len(encoded)))


def import_hexdump(input_dir, output_path, template_path=None):
    manifest_path = os.path.join(input_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as file_obj:
        manifest = json.load(file_obj)

    source_path = template_path or manifest.get("source_hex_file")
    if not source_path:
        raise ValueError("No template dump path provided. Pass --template or re-export with a newer manifest.")

    out = bytearray(load_hex_text(source_path))

    for entry in manifest["entries"]:
        if entry.get("kind") == "raw":
            record_bytes = bytes.fromhex(entry["raw_hex"])
        else:
            json_path = os.path.join(input_dir, entry["json_file"])
            with open(json_path, "r", encoding="utf-8") as file_obj:
                level_data = json.load(file_obj)
            record_bytes = build_level_bytes(level_data)

        expected_size = int(entry["record_size"])
        if len(record_bytes) != expected_size:
            raise ValueError(
                f"Edited record {entry['name']} changed size from {expected_size} to {len(record_bytes)} bytes. "
                "Keep level dimensions and total byte count the same for now."
            )

        offset = int(entry["record_offset"])
        out[offset:offset + 4] = expected_size.to_bytes(4, "little")
        out[offset + 4] = int(entry["record_flag"]) & 0xFF
        data_start = offset + 5
        data_end = data_start + expected_size
        out[data_start:data_end] = record_bytes

    hex_text = " ".join(f"{value:02X}" for value in out)
    with open(output_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(hex_text)
        file_obj.write("\n")

    print(f"Rebuilt raw playlist dump: {output_path}")


def verify_hexdump(input_dir, template_path=None):
    manifest_path = os.path.join(input_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as file_obj:
        manifest = json.load(file_obj)

    source_path = template_path or manifest.get("source_hex_file")
    if not source_path:
        raise ValueError("No template dump path provided. Pass --template or re-export with a newer manifest.")

    data = load_hex_text(source_path)
    checked = 0

    for entry in manifest["entries"]:
        if entry.get("kind") != "level":
            continue

        json_path = os.path.join(input_dir, entry["json_file"])
        with open(json_path, "r", encoding="utf-8") as file_obj:
            level_data = json.load(file_obj)

        rebuilt = build_level_bytes(level_data)
        expected_size = int(entry["record_size"])
        offset = int(entry["record_offset"])
        actual = data[offset + 5:offset + 5 + expected_size]

        if len(rebuilt) != expected_size:
            raise ValueError(
                f"{entry['name']}: rebuilt size {len(rebuilt)} does not match expected record size {expected_size}"
            )

        if rebuilt != actual:
            raise ValueError(f"{entry['name']}: JSON does not match source dump bytes at offset {offset}")

        checked += 1

    print(f"Verified {checked} level records against {source_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Export/import BattleBlock playlist raw hex dumps with UTF-16 name tables."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export a raw playlist hex dump to per-level JSON")
    export_parser.add_argument("input_text", help="Input raw hex dump file")
    export_parser.add_argument("output_dir", help="Output directory for JSON files")

    import_parser = subparsers.add_parser("import", help="Rebuild a raw playlist hex dump from per-level JSON")
    import_parser.add_argument("input_dir", help="Directory created by the export command")
    import_parser.add_argument("output_text", help="Output raw hex dump text file")
    import_parser.add_argument("--template", help="Original raw hex dump text file to patch in-place")

    verify_parser = subparsers.add_parser("verify", help="Verify exported JSON still matches a source raw hex dump")
    verify_parser.add_argument("input_dir", help="Directory created by the export command")
    verify_parser.add_argument("--template", help="Original raw hex dump text file to verify against")

    args = parser.parse_args()

    if args.command == "export":
        export_hexdump(os.path.abspath(args.input_text), os.path.abspath(args.output_dir))
        return

    if args.command == "import":
        import_hexdump(
            os.path.abspath(args.input_dir),
            os.path.abspath(args.output_text),
            os.path.abspath(args.template) if args.template else None,
        )
        return

    if args.command == "verify":
        verify_hexdump(
            os.path.abspath(args.input_dir),
            os.path.abspath(args.template) if args.template else None,
        )
        return


if __name__ == "__main__":
    main()
