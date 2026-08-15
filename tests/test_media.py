from __future__ import annotations

import base64
import hashlib

from dgx_moa.controller import Controller
from dgx_moa.media import media_assets
from dgx_moa.schemas import text_content
from dgx_moa.state import StateStore


def test_media_identity_is_bounded_and_visible_to_runtime(settings, stub_provider) -> None:  # type: ignore[no-untyped-def]
    raw = b"small-image"
    encoded = base64.b64encode(raw).decode()
    content = [
        {"type": "input_text", "text": "inspect"},
        {
            "type": "input_image",
            "image_url": f"data:image/png;base64,{encoded}",
            "width": 2,
            "height": 3,
        },
    ]

    assets = media_assets(content)
    assert assets == [
        {
            "asset_id": f"asset_{hashlib.sha256(raw).hexdigest()[:24]}",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "media_type": "image/png",
            "dimensions": {"width": 2, "height": 3},
            "source": "input_image",
            "storage_reference": "data:image/png;base64",
            "redaction_status": "redacted",
        }
    ]
    assert encoded not in str(assets)
    assert "[media image/png asset_" in text_content(content)

    controller = Controller(settings, StateStore(settings.state_db), stub_provider)
    state = controller.session("media-session", [{"role": "user", "content": content}])
    snapshot = controller.runtime_evidence_snapshot(state)
    constraints = snapshot.request_constraints_json[0]
    assert state.media_assets == assets
    assert assets[0]["asset_id"] in constraints
    assert encoded not in state.model_dump_json()


def test_remote_media_reference_drops_query_and_reports_unknown_content_hash() -> None:
    asset = media_assets(
        [
            {
                "type": "image_url",
                "image_url": {"url": "https://user:password@example.invalid/a.png?token=secret#x"},
            }
        ]
    )[0]

    assert asset["sha256"] is None
    assert asset["storage_reference"] == "https://example.invalid/a.png"
    assert asset["redaction_status"] == "redacted"
