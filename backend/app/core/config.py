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
    LLM_PROVIDER: str = Field(
        default="ollama",
        description="LLM provider: 'ollama', 'gemini', or 'qwen'",
    )

    # --- Ollama ---
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", description="Ollama server URL")
    OLLAMA_MODEL: str = Field(default="llama3.1", description="Ollama model name")

    # --- Gemini ---
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key")
    GEMINI_MODEL: str = Field(default="gemini-3-flash-preview", description="Gemini model name")

    # --- Qwen / OpenAI-compatible endpoint ---
    QWEN_BASE_URL: str = Field(default="", description="OpenAI-compatible Qwen server URL")
    QWEN_API_KEY: str = Field(default="dummy", description="Qwen API key placeholder")
    QWEN_MODEL: str = Field(default="Qwen3.6-35B", description="Qwen model name")
    QWEN_TIMEOUT_SECONDS: int = Field(default=120, description="Qwen request timeout")
    QWEN_ENABLE_THINKING: bool = Field(
        default=False,
        description="Enable Qwen reasoning/thinking output when supported",
    )

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
        default=0.2,
        description="Minimum confidence threshold for findings (0.0-1.0)",
    )
    AGENT_TIMEOUT_SECONDS: int = Field(
        default=120,
        description="Maximum seconds to wait for each agent result",
    )
    LLM_MAX_OUTPUT_TOKENS: int = Field(
        default=8192,
        description="Maximum generated tokens requested from the LLM",
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
