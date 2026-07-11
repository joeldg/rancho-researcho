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
    search_base_url: HttpUrl | None = None
    search_api_key: str | None = None
    max_results: int = Field(default=10, ge=1, le=20)
    llm_provider: str | None = None
    llm_base_url: HttpUrl | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_complex_model: str | None = None

    @property
    # @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
    def search_is_configured(self) -> bool:
        """Whether a search provider has the minimum adapter configuration."""
        return bool(self.search_provider == "searxng" and self.search_base_url)

    @property
    def llm_is_configured(self) -> bool:
        """Whether the approved local LLM client has required configuration."""
        return bool(
            self.llm_provider in {"ollama", "vllm"}
            and self.llm_base_url
            and self.llm_model
        )


@lru_cache
# @spec[RANCHO_API_SECURITY.md#provider-configuration-and-searxng]
def get_settings() -> Settings:
    """Return cached validated application settings."""
    return Settings()
