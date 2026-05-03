"""
LLM Service — LangChain LLM factory for Ollama and Gemini.

Creates the appropriate LangChain chat model based on configuration.
"""
import logging
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import Settings

logger = logging.getLogger(__name__)


def get_llm(settings: Settings) -> BaseChatModel:
    """
    Create a LangChain chat model based on the configured provider.

    Args:
        settings: Application settings

    Returns:
        LangChain BaseChatModel instance

    Raises:
        ValueError: If the provider is not supported
    """
    provider = settings.LLM_PROVIDER.lower()

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        logger.info(f"Initializing Ollama LLM: {settings.OLLAMA_MODEL} at {settings.OLLAMA_BASE_URL}")
        return ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            temperature=0.1,
            num_predict=8192,
        )

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is required when using 'gemini' provider")

        logger.info(f"Initializing Gemini LLM: {settings.GEMINI_MODEL}")
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.1,
            max_output_tokens=8192,
        )

    else:
        raise ValueError(
            f"Unsupported LLM provider: '{provider}'. "
            f"Supported: 'ollama', 'gemini'"
        )
