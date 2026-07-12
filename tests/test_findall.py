"""Contract tests for schema-valid, evidence-linked FindAll candidates."""

import json
import uuid
from datetime import datetime, timezone

from rancho.db_models import Evidence
from rancho.findall import validate_candidates


def _evidence(task_id):
    return Evidence(
        id=uuid.uuid4(),
        task_id=task_id,
        canonical_url="https://example.com/company",
        original_url="https://example.com/company",
        content="Acme is an EV company in California.",
        content_sha256="0" * 64,
        retrieved_at=datetime.now(timezone.utc),
    )


# @spec[RANCHO_FINDALL_AND_MONITORS.md#acceptance-evidence]
def test_candidates_require_exact_schema_and_task_evidence():
    task_id = uuid.uuid4()
    retained = _evidence(task_id)
    other = _evidence(uuid.uuid4())
    response = json.dumps(
        {
            "candidates": [
                {
                    "fields": {"name": "Acme", "active": True},
                    "evidence_ids": [str(retained.id)],
                },
                {
                    "fields": {"name": "Unknown", "active": True},
                    "evidence_ids": [str(other.id)],
                },
                {
                    "fields": {"name": "Extra", "active": True, "city": "LA"},
                    "evidence_ids": [str(retained.id)],
                },
                {
                    "fields": {"name": "Wrong type", "active": "yes"},
                    "evidence_ids": [str(retained.id)],
                },
            ]
        }
    )

    verified = validate_candidates(
        response, {"name": "string", "active": "boolean"}, [retained]
    )

    assert len(verified) == 1
    assert verified[0].data == {"name": "Acme", "active": True}
    assert [item.id for item in verified[0].evidence] == [retained.id]


# @spec[RANCHO_FINDALL_AND_MONITORS.md#requirements]
def test_model_prose_is_not_a_candidate_result():
    assert validate_candidates(
        json.dumps({"candidates": ["Acme is probably a match."]}),
        {"name": "string"},
        [_evidence(uuid.uuid4())],
    ) == []
