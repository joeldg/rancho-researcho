"""Contract tests for schema-valid, evidence-linked FindAll candidates."""

import json
import uuid
from datetime import datetime, timezone

from rancho.db_models import Evidence
from rancho.findall import extract_candidates, validate_candidates


class _LLM:
    def __init__(self, response):
        self.response = response
        self.messages = None

    def complete(self, messages, **kwargs):
        del kwargs
        self.messages = messages
        return self.response


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
                    "match_status": "matched",
                    "reasoning": "The retained profile supports the match.",
                },
                {
                    "fields": {"name": "Unknown", "active": True},
                    "evidence_ids": [str(other.id)],
                    "match_status": "matched",
                    "reasoning": "Cross-task support is invalid.",
                },
                {
                    "fields": {"name": "Extra", "active": True, "city": "LA"},
                    "evidence_ids": [str(retained.id)],
                    "match_status": "matched",
                    "reasoning": "Unknown fields are invalid.",
                },
                {
                    "fields": {"name": "Wrong type", "active": "yes"},
                    "evidence_ids": [str(retained.id)],
                    "match_status": "matched",
                    "reasoning": "Wrong types are invalid.",
                },
            ]
        }
    )

    verified = validate_candidates(
        response, {"name": "string", "active": "boolean"}, [retained]
    )

    assert len(verified) == 1
    assert verified[0].data == {"name": "Acme", "active": True}
    assert verified[0].reasoning == "The retained profile supports the match."
    assert [item.id for item in verified[0].evidence] == [retained.id]


# @spec[RANCHO_FINDALL_AND_MONITORS.md#requirements]
def test_model_prose_is_not_a_candidate_result():
    assert (
        validate_candidates(
            json.dumps({"candidates": ["Acme is probably a match."]}),
            {"name": "string"},
            [_evidence(uuid.uuid4())],
        )
        == []
    )


def test_fenced_empty_candidate_result_is_an_honest_empty_result():
    assert (
        validate_candidates(
            'No supported matches were found.\n```json\n{"candidates":[]}\n```',
            {"name": "string"},
            [_evidence(uuid.uuid4())],
        )
        == []
    )


def test_candidate_prompt_is_bounded_across_many_large_evidence_rows():
    evidence = [_evidence(uuid.uuid4()) for _ in range(20)]
    for item in evidence:
        item.title = "Source"
        item.content = "retained evidence " * 2_000
    llm = _LLM('{"candidates":[]}')

    assert extract_candidates(
        llm,
        "Find documented projects",
        {"name": "string", "license": "string"},
        evidence,
        256,
    ) == []
    assert len(llm.messages[1]["content"]) < 12_000
