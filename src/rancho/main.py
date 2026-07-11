"""FastAPI entry point for Rancho Researcho."""

from uuid import uuid4

from fastapi import Depends, FastAPI, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse

from rancho.config import Settings, get_settings
from rancho.models import ErrorResponse, SearchRequest, SearchResponse

app = FastAPI(
    title="Rancho Researcho",
    version="0.1.0",
    description="A self-hosted, evidence-first web research service.",
)


# @spec[RANCHO_API_SECURITY.md#requirements]
@app.get("/health")
def health() -> dict[str, str]:
    """Return process health without exposing configuration or secrets."""
    return {"status": "ok"}


# @spec[RANCHO_API_SECURITY.md#requirements]
@app.get("/ready")
def ready(settings: Settings = Depends(get_settings)) -> Response:
    """Report whether a search adapter is configured for traffic."""
    if settings.search_is_configured:
        return JSONResponse({"status": "ready"})
    return JSONResponse(
        {"status": "not_ready", "reason": "search_provider_unconfigured"},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


# @spec[RANCHO_API_SECURITY.md#requirements]
@app.get("/metrics", response_class=PlainTextResponse)
def metrics(settings: Settings = Depends(get_settings)) -> str:
    """Expose a minimal Prometheus-compatible configuration health signal."""
    configured = int(settings.search_is_configured)
    return (
        "# HELP rancho_search_provider_configured "
        "Whether a search provider is configured.\n"
        "# TYPE rancho_search_provider_configured gauge\n"
        f"rancho_search_provider_configured {configured}\n"
    )


# @spec[RANCHO_API_SECURITY.md#requirements]
@app.post(
    "/v1/search",
    response_model=SearchResponse,
    responses={503: {"model": ErrorResponse}},
)
@app.post(
    "/search",
    response_model=SearchResponse,
    responses={503: {"model": ErrorResponse}},
    include_in_schema=False,
)
def search(
    request: SearchRequest,
    settings: Settings = Depends(get_settings),
) -> SearchResponse | JSONResponse:
    """Serve a bounded search request or an explicit unavailable-provider error.

    A configured adapter is intentionally required before this endpoint returns
    results. The Phase 1 scaffold never fabricates search results or citations.
    """
    del request
    request_id = f"req_{uuid4().hex}"
    if not settings.search_is_configured:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(
                error={
                    "code": "provider_unavailable",
                    "message": "No search provider is configured.",
                },
                request_id=request_id,
            ).model_dump(mode="json"),
        )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=ErrorResponse(
            error={
                "code": "provider_unavailable",
                "message": "The configured search adapter is not implemented yet.",
            },
            request_id=request_id,
        ).model_dump(mode="json"),
    )
