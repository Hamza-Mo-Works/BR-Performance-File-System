"""Write imaginary binary containers. These are not ECU firmware.

Format: 8-byte magic + 4-byte big-endian JSON length + UTF-8 JSON + payload.
Step 4 will add the upload parser for this format.
"""
import hashlib
import json
import random
import struct
from pathlib import Path

MAGIC = b"BRDEMO1\x00"
PAYLOAD_SIZE = 4096


def build_demo_binary(metadata, seed, file_kind="ORIGINAL_DEMO"):
    header = dict(metadata)
    header.update(schema_version=1, is_synthetic=True,
                  file_kind=file_kind, payload_size=PAYLOAD_SIZE)
    encoded = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    generator = random.Random(seed)
    payload = bytes(generator.randrange(256) for _ in range(PAYLOAD_SIZE))
    return MAGIC + struct.pack(">I", len(encoded)) + encoded + payload


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write_generated_file(path, content):
    """Reruns preserve identical files and refuse to overwrite changed ones."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Existing file differs; left unchanged: {path}")
        return
    path.write_bytes(content)
