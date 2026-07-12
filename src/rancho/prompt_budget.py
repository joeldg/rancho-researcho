"""Deterministic prompt serialization within the local LLM message bound."""

from __future__ import annotations

import json
from typing import Any

_MAX_USER_MESSAGE_CHARS = 11_000


def serialize_bounded_evidence_payload(payload: dict[str, Any]) -> str:
    """Serialize an evidence payload while fitting its content to 11k chars.

    Evidence identity and canonical metadata are always retained. Content is
    distributed evenly and reduced using the actual serialized size, which also
    accounts for JSON escaping and metadata overhead.
    """
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return json.dumps(payload, separators=(",", ":"))

    contents = [str(item.get("content", "")) for item in evidence]
    quota = max((len(value) for value in contents), default=0)
    while True:
        bounded = {
            **payload,
            "evidence": [
                {**item, "content": content[:quota]}
                for item, content in zip(evidence, contents, strict=True)
            ],
        }
        serialized = json.dumps(bounded, separators=(",", ":"))
        if len(serialized) <= _MAX_USER_MESSAGE_CHARS:
            return serialized
        if quota == 0:
            raise ValueError("evidence metadata exceeds the prompt bound")
        scaled_quota = quota * _MAX_USER_MESSAGE_CHARS // len(serialized)
        quota = max(0, min(quota - 1, scaled_quota))
