import hashlib


def sha256_hex(text: str) -> str:
    """Return the SHA-256 digest of a text as a hexadecimal string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
