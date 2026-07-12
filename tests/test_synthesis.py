"""Contract tests for untrusted claim verification and canonical citations."""

import json
import uuid
from datetime import datetime, timezone

from rancho.db_models import Evidence
from rancho.synthesis import render_verified_claims, verify_candidates


def _evidence(task_id, url):
    return Evidence(
        id=uuid.uuid4(),
        task_id=task_id,
        canonical_url=url,
        original_url=url,
        title="Retained source",
        content="Retained fact.",
        content_sha256="0" * 64,
        retrieved_at=datetime.now(timezone.utc),
    )


def _candidate(text, evidence_ids, citation_urls):
    return {
        "text": text,
        "evidence_ids": [str(value) for value in evidence_ids],
        "citation_urls": citation_urls,
    }


# @spec[RANCHO_CLAIM_VERIFICATION.md#acceptance-evidence]
def test_rejects_unknown_and_cross_task_evidence_ids():
    task_id = uuid.uuid4()
    retained = _evidence(task_id, "https://example.com/retained")
    cross_task = _evidence(uuid.uuid4(), "https://example.com/other")
    payload = {
        "claims": [
            _candidate("Unknown support", [uuid.uuid4()], []),
            _candidate("Cross-task support", [cross_task.id], []),
            _candidate("Auditable support", [retained.id], []),
        ]
    }

    verified = verify_candidates(json.dumps(payload), [retained])

    assert [claim.text for claim in verified] == ["Auditable support"]


# @spec[RANCHO_CLAIM_VERIFICATION.md#acceptance-evidence]
def test_rejects_absent_url_and_omits_unsupported_claims():
    retained = _evidence(uuid.uuid4(), "https://example.com/canonical")
    payload = {
        "claims": [
            _candidate(
                "A fabricated citation https://unknown.example/fact",
                [retained.id],
                ["https://unknown.example/fact"],
            ),
            _candidate("No evidence", [], []),
            _candidate(
                "Verified fact",
                [retained.id],
                ["https://example.com/canonical"],
            ),
        ]
    }

    verified = verify_candidates(json.dumps(payload), [retained])

    assert [claim.text for claim in verified] == ["Verified fact"]
    rendered = render_verified_claims(verified)
    assert rendered == (
        f"- Verified fact [evidence:{retained.id}](https://example.com/canonical)"
    )
    assert "unknown.example" not in rendered
