from __future__ import annotations

import base64
import binascii
import hashlib
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

MEDIA_TYPES = {"image", "image_url", "input_image"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _reference(part: dict[str, Any]) -> str | None:
    value = part.get("image_url", part.get("url", part.get("file_id")))
    if isinstance(value, dict):
        value = value.get("url")
    return value if isinstance(value, str) and value else None


def _redacted_reference(reference: str) -> tuple[str, str]:
    if reference.startswith("data:"):
        return reference.partition(",")[0], "redacted"
    parsed = urlsplit(reference)
    if parsed.scheme in {"http", "https"}:
        hostname = parsed.hostname or ""
        hostname = f"[{hostname}]" if ":" in hostname else hostname
        try:
            port = parsed.port
        except ValueError:
            port = None
        netloc = f"{hostname}:{port}" if port is not None else hostname
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", "")), (
            "redacted"
            if parsed.username or parsed.password or parsed.query or parsed.fragment
            else "not_required"
        )
    return reference, "not_required"


def _inline_identity(reference: str) -> tuple[str | None, str | None]:
    if not reference.startswith("data:"):
        return None, None
    header, separator, encoded = reference.partition(",")
    media_type = header[5:].split(";", 1)[0] or "application/octet-stream"
    if not separator or ";base64" not in header:
        return media_type, None
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return media_type, None
    return media_type, hashlib.sha256(raw).hexdigest()


def media_assets(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    assets: list[dict[str, Any]] = []
    for part in value:
        if not isinstance(part, dict) or part.get("type") not in MEDIA_TYPES:
            continue
        reference = _reference(part)
        if reference is None:
            continue
        inline_type, inline_sha = _inline_identity(reference)
        supplied_sha = str(part.get("sha256", "")).lower()
        digest = supplied_sha if SHA256.fullmatch(supplied_sha) else inline_sha
        stored_reference, redaction_status = _redacted_reference(reference)
        identity = digest or hashlib.sha256(reference.encode()).hexdigest()
        width, height = part.get("width"), part.get("height")
        dimensions = (
            {"width": width, "height": height}
            if type(width) is int and width > 0 and type(height) is int and height > 0
            else None
        )
        assets.append(
            {
                "asset_id": f"asset_{identity[:24]}",
                "sha256": digest,
                "media_type": str(part.get("media_type") or inline_type or "image/unknown"),
                "dimensions": dimensions,
                "source": str(part.get("type")),
                "storage_reference": stored_reference,
                "redaction_status": redaction_status,
            }
        )
    return assets


def media_placeholders(value: Any) -> list[str]:
    return [f"[media {asset['media_type']} {asset['asset_id']}]" for asset in media_assets(value)]
