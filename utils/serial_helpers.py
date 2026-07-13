"""Shared serial utility helpers."""


def parse_line_ending(line_ending: str, default: bytes = b"\r\n") -> bytes:
    """Safely parse line_ending hex string to bytes."""
    if not line_ending:
        return default
    le = line_ending.strip().lower()
    if le in ("none", "null", ""):
        return b""
    try:
        return bytes.fromhex(le.replace(" ", ""))
    except ValueError:
        return default
