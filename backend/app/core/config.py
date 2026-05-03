"""
Code Review Bot — Core Configuration

Loads environment variables and provides typed settings via Pydantic.
Extended with multi-agent system settings.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- LLM Provider ---
    LLM_PROVIDER: str = Field(default="ollama", description="LLM provider: 'ollama' or 'gemini'")

    # --- Ollama ---
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", description="Ollama server URL")
    OLLAMA_MODEL: str = Field(default="llama3.1", description="Ollama model name")

    # --- Gemini ---
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key")
    GEMINI_MODEL: str = Field(default="gemini-3-flash-preview", description="Gemini model name")

    # --- GitHub ---
    GITHUB_TOKEN: str = Field(default="", description="GitHub personal access token (optional)")

    # --- AACR-Bench ---
    AACR_BENCH_PATH: str = Field(default="../../aacr-bench", description="Path to AACR-Bench repo")

    # --- Multi-Agent System ---
    AGENT_PARALLEL: bool = Field(
        default=True,
        description="Run agents in parallel (True) or sequential (False)",
    )
    AGENT_CONFIDENCE_THRESHOLD: float = Field(
        default=0.3,
        description="Minimum confidence threshold for findings (0.0-1.0)",
    )
    MAX_FILE_CONTEXT_CHARS: int = Field(
        default=10000,
        description="Maximum characters of full file content to include per file",
    )
    VERIFICATION_ENABLED: bool = Field(
        default=True,
        description="Enable consensus verification and deduplication",
    )

    # --- Server ---
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(default=8000, description="Server port")
    DEBUG: bool = Field(default=True, description="Debug mode")

    model_config = {
        "env_file": str(Path(__file__).parent.parent.parent / ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
