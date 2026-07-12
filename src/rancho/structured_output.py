"""Bounded extraction of one JSON object from untrusted model output."""

from __future__ import annotations

import json
from typing import Any

_MAX_RESPONSE_CHARS = 24_000


class StructuredOutputError(ValueError):
    """Raised when a model response has no unambiguous JSON object."""


def parse_single_json_object(response: str) -> dict[str, Any]:
    """Return the response's only JSON object, allowing harmless wrappers.

    Local models sometimes surround an otherwise valid response with a Markdown
    fence or a short explanation.  This function tolerates that transport noise
    without interpreting it: exactly one decodable JSON object must exist, and
    all schema and evidence checks remain the caller's responsibility.
    """
    if not isinstance(response, str) or not response.strip():
        raise StructuredOutputError
    if len(response) > _MAX_RESPONSE_CHARS:
        raise StructuredOutputError

    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    index = 0
    while True:
        start = response.find("{", index)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(response, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(value, dict):
            objects.append(value)
        index = max(end, start + 1)

    if len(objects) != 1:
        raise StructuredOutputError
    return objects[0]
