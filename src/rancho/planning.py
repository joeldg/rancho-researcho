"""Bounded local-LLM planning for deep research."""

import json
import re

from rancho.llm import LLMUnavailableError, LocalLLMClient
from rancho.structured_output import StructuredOutputError, parse_single_json_object

_MAX_QUERY_CHARS = 2_000


# @spec[RANCHO_DEEP_RESEARCH_LOOP.md#requirements]
def plan_queries(
    llm: LocalLLMClient, objective: str, limit: int, tokens: int
) -> list[str]:
    """Return bounded structured search queries without executing model prose."""
    try:
        response = llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        'Return JSON only: {"queries":[string]}. Return at most '
                        f"{limit} queries. Create "
                        "focused queries that prioritize authoritative primary "
                        "sources: official documentation, maintainers, standards "
                        "bodies, government sources, and original research. Use "
                        "site: constraints when the objective names or clearly "
                        "implies an authoritative organization. Use simple search "
                        "keywords; avoid parentheses, Boolean OR groups, and long "
                        "quoted phrases. Cover distinct parts of the objective and "
                        "do not invent facts."
                    ),
                },
                {"role": "user", "content": f"Objective: {objective}"},
            ],
            high_effort=True,
            max_output_tokens=tokens,
        )
    except LLMUnavailableError:
        return []
    try:
        payload = parse_single_json_object(response)
    except StructuredOutputError:
        return _fallback_site_queries(response, limit)
    if not isinstance(payload, dict) or set(payload) != {"queries"}:
        return []
    raw_queries = payload["queries"]
    if not isinstance(raw_queries, list):
        return []
    queries: list[str] = []
    for value in raw_queries[:limit]:
        if isinstance(value, dict) and set(value) == {"query", "rationale"}:
            rationale = value["rationale"]
            if not isinstance(rationale, str) or len(rationale) > 1_000:
                return []
            value = value["query"]
        if not isinstance(value, str):
            return []
        query = value.strip()
        if not query or len(query) > _MAX_QUERY_CHARS:
            return []
        if query not in queries:
            queries.append(query)
    return queries


def _fallback_site_queries(response: str, limit: int) -> list[str]:
    """Recover only explicit authoritative queries from weak model wrappers."""
    values: list[str] = []
    fenced = re.findall(r"```(?:[a-zA-Z]+)?\s*\n(.*?)```", response, re.DOTALL)
    for block in fenced:
        query = " ".join(block.strip().splitlines())
        if not query.startswith("{"):
            values.append(query)
    # A token-limited response can contain complete JSON string values before
    # its outer object is truncated. Decode string tokens; never regex-unescape.
    for token in re.findall(r'"(?:\\.|[^"\\])*"', response):
        try:
            value = json.loads(token)
        except json.JSONDecodeError:
            continue
        if isinstance(value, str):
            values.append(value)

    queries: list[str] = []
    for value in values:
        query = value.strip()
        if (
            "site:" not in query.lower()
            or not query
            or len(query) > _MAX_QUERY_CHARS
            or query in queries
        ):
            continue
        queries.append(query)
        if len(queries) == limit:
            break
    return queries
