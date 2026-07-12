"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


# @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
class Settings(BaseSettings):
    """Runtime settings for the Rancho API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RANCHO_",
        env_ignore_empty=True,
        extra="ignore",
    )

    environment: str = Field(default="development", validation_alias="RANCHO_ENV")
    public_base_url: HttpUrl | None = None
    search_provider: str | None = None
    search_providers: str | None = None
    search_base_url: HttpUrl | None = None
    search_api_key: str | None = None
    bing_api_key: str | None = None
    max_results: int = Field(default=10, ge=1, le=20)
    search_enrich: bool = False
    search_enrich_max_results: int = Field(default=3, ge=1, le=10)
    llm_provider: str | None = None
    llm_base_url: HttpUrl | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_complex_model: str | None = None
    research_planning: bool = True
    research_max_iterations: int = Field(default=2, ge=1, le=5)
    research_max_elapsed_seconds: int = Field(default=120, ge=5, le=600)
    research_max_planner_tokens: int = Field(default=256, ge=32, le=1024)
    research_max_model_tokens: int = Field(default=4096, ge=128, le=16384)
    database_url: str | None = None
    redis_url: str | None = None

    # @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
    def async_database_url(self) -> str | None:
        """Return the durable-store URL with an async driver, if configured."""
        if not self.database_url:
            return None
        for prefix in ("postgresql://", "postgres://"):
            if self.database_url.startswith(prefix):
                return "postgresql+asyncpg://" + self.database_url[len(prefix) :]
        return self.database_url

    # @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
    def active_search_providers(self) -> list[str]:
        """Return the operator-selected providers that are actually buildable.

        Selection is explicit operator configuration and is never derived from a
        caller request or a search result. `RANCHO_SEARCH_PROVIDERS` (a comma list
        of `searxng`, `duckduckgo`, `bing`) takes precedence; when it is unset the
        legacy single-SearXNG configuration is preserved.
        """
        if self.search_providers:
            names = [
                name.strip().lower()
                for name in self.search_providers.split(",")
                if name.strip()
            ]
        elif self.search_provider == "searxng" and self.search_base_url:
            names = ["searxng"]
        else:
            names = []

        active: list[str] = []
        for name in names:
            if name in active:
                continue
            if name == "searxng" and self.search_base_url:
                active.append(name)
            elif name == "duckduckgo":
                active.append(name)
            elif name == "bing" and self.bing_api_key:
                active.append(name)
        return active

    @property
    # @spec[RANCHO_SEARCH_ORCHESTRATION.md#requirements]
    def search_is_configured(self) -> bool:
        """Whether at least one active search provider is configured."""
        return bool(self.active_search_providers())

    @property
    def llm_is_configured(self) -> bool:
        """Whether the approved local LLM client has required configuration."""
        return bool(
            self.llm_provider in {"ollama", "vllm"}
            and self.llm_base_url
            and self.llm_model
        )

    @property
    # @spec[RANCHO_SNIPPET_SYNTHESIS.md#requirements]
    def enrich_is_enabled(self) -> bool:
        """Whether LLM snippet enrichment is turned on and can run."""
        return bool(self.search_enrich and self.llm_is_configured)


@lru_cache
# @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
def get_settings() -> Settings:
    """Return cached validated application settings."""
    return Settings()
