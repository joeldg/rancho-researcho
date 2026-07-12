"""Claim-backed synthesis over retained task evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from rancho.db_models import Evidence
from rancho.llm import LLMUnavailableError, LocalLLMClient
from rancho.prompt_budget import serialize_bounded_evidence_payload
from rancho.structured_output import StructuredOutputError, parse_single_json_object

_MAX_CLAIMS = 50
_MAX_CLAIM_LENGTH = 2_000
_URL_PATTERN = re.compile(r"https?://[^\s)\]>]+")


class VerificationUnavailableError(Exception):
    """Raised when untrusted model output cannot be safely verified."""


@dataclass(frozen=True)
class VerifiedClaim:
    """A bounded claim whose evidence belongs to the current task."""

    text: str
    evidence: tuple[Evidence, ...]


# @spec[RANCHO_CLAIM_VERIFICATION.md#requirements]
def synthesize_claims(
    llm: LocalLLMClient,
    objective: str,
    evidence: list[Evidence],
    max_output_tokens: int = 1_024,
) -> list[VerifiedClaim]:
    """Generate candidates and retain only claims supported by task evidence."""
    if not evidence:
        raise VerificationUnavailableError
    bundle = [
        {
            "evidence_id": str(item.id),
            "canonical_url": item.canonical_url,
            "title": item.title,
            "content": item.content,
        }
        for item in evidence
    ]
    try:
        response = llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        'Return JSON only: {"claims":[{"text":string,'
                        '"evidence_ids":[uuid],"citation_urls":[url]}]}. '
                        "Use only the supplied evidence. Omit unsupported claims."
                    ),
                },
                {
                    "role": "user",
                    "content": serialize_bounded_evidence_payload(
                        {"objective": objective, "evidence": bundle}
                    ),
                },
            ],
            high_effort=True,
            max_output_tokens=max_output_tokens,
        )
    except LLMUnavailableError as error:
        raise VerificationUnavailableError from error
    return verify_candidates(response, evidence)


# @spec[RANCHO_CLAIM_VERIFICATION.md#requirements]
def verify_candidates(
    response: str, task_evidence: list[Evidence]
) -> list[VerifiedClaim]:
    """Validate untrusted candidate IDs, ownership, URLs, and bounded text."""
    try:
        payload = parse_single_json_object(response)
    except StructuredOutputError as error:
        raise VerificationUnavailableError from error
    if not isinstance(payload, dict) or set(payload) != {"claims"}:
        raise VerificationUnavailableError
    candidates = payload["claims"]
    if not isinstance(candidates, list) or len(candidates) > _MAX_CLAIMS:
        raise VerificationUnavailableError

    retained = {item.id: item for item in task_evidence}
    verified: list[VerifiedClaim] = []
    for candidate in candidates:
        claim = _verify_candidate(candidate, retained)
        if claim is not None:
            verified.append(claim)
    return verified


def _verify_candidate(
    candidate: Any, retained: dict[UUID, Evidence]
) -> VerifiedClaim | None:
    if not isinstance(candidate, dict) or set(candidate) != {
        "text",
        "evidence_ids",
        "citation_urls",
    }:
        return None
    text = candidate["text"]
    evidence_ids = candidate["evidence_ids"]
    citation_urls = candidate["citation_urls"]
    if (
        not isinstance(text, str)
        or not text.strip()
        or len(text.strip()) > _MAX_CLAIM_LENGTH
        or not isinstance(evidence_ids, list)
        or not evidence_ids
        or not isinstance(citation_urls, list)
        or not all(isinstance(url, str) for url in citation_urls)
    ):
        return None
    try:
        ids = tuple(dict.fromkeys(UUID(value) for value in evidence_ids))
    except (TypeError, ValueError, AttributeError):
        return None
    if not ids or any(evidence_id not in retained for evidence_id in ids):
        return None
    linked = tuple(retained[evidence_id] for evidence_id in ids)
    allowed_urls = {item.canonical_url for item in linked}
    mentioned_urls = set(citation_urls) | set(_URL_PATTERN.findall(text))
    if not mentioned_urls <= allowed_urls:
        return None
    return VerifiedClaim(text=text.strip(), evidence=linked)


# @spec[RANCHO_CLAIM_VERIFICATION.md#requirements]
def render_verified_claims(claims: list[VerifiedClaim]) -> str:
    """Render canonical citations that identify each linked evidence row."""
    lines = []
    for claim in claims:
        citations = " ".join(
            f"[evidence:{item.id}]({item.canonical_url})" for item in claim.evidence
        )
        lines.append(f"- {claim.text} {citations}")
    return "\n".join(lines)
