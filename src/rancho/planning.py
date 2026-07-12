"""Bounded local-LLM planning for deep research."""

from rancho.llm import LLMUnavailableError, LocalLLMClient


# @spec[RANCHO_DEEP_RESEARCH_LOOP.md#requirements]
def plan_queries(
    llm: LocalLLMClient, objective: str, limit: int, tokens: int
) -> list[str]:
    """Return bounded plain-text search queries without executing model text."""
    try:
        response = llm.complete(
            [
                {
                    "role": "system",
                    "content": "Return one web search query per line; no prose.",
                },
                {"role": "user", "content": f"Objective: {objective}"},
            ],
            high_effort=True,
            max_output_tokens=tokens,
        )
    except LLMUnavailableError:
        return []
    queries = []
    for line in response.splitlines():
        query = line.lstrip("-0123456789. ").strip()[:2000]
        if query and query not in queries:
            queries.append(query)
        if len(queries) == limit:
            break
    return queries
