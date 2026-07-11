"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Optional

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


# @spec[RANCHO_API_SECURITY.md#requirements]
class Settings(BaseSettings):
    """Runtime settings for the Rancho API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RANCHO_",
        extra="ignore",
    )

    environment: str = Field(default="development", validation_alias="RANCHO_ENV")
    public_base_url: Optional[HttpUrl] = None
    search_provider: Optional[str] = None
    search_base_url: Optional[HttpUrl] = None
    search_api_key: Optional[str] = None
    max_results: int = Field(default=10, ge=1, le=20)

    @property
    # @spec[RANCHO_API_SECURITY.md#requirements]
    def search_is_configured(self) -> bool:
        """Whether a search provider has the minimum adapter configuration."""
        return bool(self.search_provider and self.search_base_url)


@lru_cache
# @spec[RANCHO_API_SECURITY.md#requirements]
def get_settings() -> Settings:
    """Return cached validated application settings."""
    return Settings()
