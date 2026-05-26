"""
LLM Service — LangChain LLM factory for Ollama and Gemini.

Creates the appropriate LangChain chat model based on configuration.
"""
import logging
import json
import re
from typing import Any, List, Optional

import requests
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import Settings

logger = logging.getLogger(__name__)


class OpenAICompatibleChatModel(BaseChatModel):
    """Minimal LangChain chat wrapper for vLLM/OpenAI-compatible endpoints."""

    base_url: str
    api_key: str = "dummy"
    model: str
    temperature: float = 0.1
    max_tokens: int = 8192
    timeout: int = 120
    enable_thinking: bool = False

    @property
    def _llm_type(self) -> str:
        return "openai-compatible"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = {
            "model": self.model,
            "messages": [self._convert_message(message) for message in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if not self.enable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        if stop:
            payload["stop"] = stop

        data = self._post_chat_completion(payload)
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        raw_content = message.get("content", "")
        content = self._normalize_json_array_response(raw_content)
        if content == "[]" and raw_content.strip() not in {"", "[]"}:
            logger.warning(
                "Qwen response did not contain a valid JSON array; "
                "discarding raw output preview: %s",
                raw_content[:1000],
            )

        generation = ChatGeneration(
            message=AIMessage(
                content=content,
                response_metadata={
                    "model": data.get("model", self.model),
                    "finish_reason": choice.get("finish_reason"),
                },
            )
        )
        return ChatResult(generations=[generation])

    def _post_chat_completion(self, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key or 'dummy'}",
            "Content-Type": "application/json",
        }
        urls = [f"{self.base_url.rstrip('/')}/chat/completions"]
        if not self.base_url.rstrip("/").endswith("/v1"):
            urls.append(f"{self.base_url.rstrip('/')}/v1/chat/completions")

        last_error = None
        for url in urls:
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                if response.status_code == 404 and url == urls[0] and len(urls) > 1:
                    last_error = response
                    continue
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if url != urls[-1]:
                    continue
                raise

        if isinstance(last_error, requests.Response):
            last_error.raise_for_status()
        raise RuntimeError("OpenAI-compatible chat completion failed")

    @staticmethod
    def _convert_message(message: BaseMessage) -> dict:
        role_by_type = {
            "system": "system",
            "human": "user",
            "ai": "assistant",
            "chat": "user",
        }
        role = role_by_type.get(message.type, message.type)
        return {"role": role, "content": message.content}

    @classmethod
    def _normalize_json_array_response(cls, content: str) -> str:
        """
        Keep the agent contract stable for Qwen/vLLM.

        The review agents already instruct the model to return only a JSON
        array. Qwen reasoning models may prepend thinking/prose; passing that
        through lets the fallback markdown parser turn reasoning text into fake
        findings. For this provider, only a parseable JSON array is accepted.
        """
        text = re.sub(r"<think>.*?</think>", "", content or "", flags=re.DOTALL).strip()
        array_text = cls._extract_json_array(text)
        if not array_text:
            return "[]"
        try:
            parsed = json.loads(array_text)
        except (json.JSONDecodeError, TypeError):
            return "[]"
        return array_text if isinstance(parsed, list) else "[]"

    @staticmethod
    def _extract_json_array(text: str) -> str:
        start = text.find("[")
        if start < 0:
            return ""

        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(text)):
            char = text[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return text[start:idx + 1]
        return ""


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
            num_predict=settings.LLM_MAX_OUTPUT_TOKENS,
        )

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is required when using 'gemini' provider")

        logger.info(
            "Initializing Gemini LLM: %s (max_tokens=%s)",
            settings.GEMINI_MODEL,
            settings.LLM_MAX_OUTPUT_TOKENS,
        )
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.1,
            max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
        )

    elif provider in {"qwen", "openai_compatible"}:
        base_url = settings.OPENAI_COMPATIBLE_BASE_URL or settings.QWEN_BASE_URL
        api_key = settings.OPENAI_COMPATIBLE_API_KEY or settings.QWEN_API_KEY or "dummy"
        model = settings.OPENAI_COMPATIBLE_MODEL or settings.QWEN_MODEL
        timeout = (
            settings.OPENAI_COMPATIBLE_TIMEOUT_SECONDS
            or settings.QWEN_TIMEOUT_SECONDS
        )
        enable_thinking = (
            settings.OPENAI_COMPATIBLE_ENABLE_THINKING
            or settings.QWEN_ENABLE_THINKING
        )

        if not base_url:
            raise ValueError(
                "OPENAI_COMPATIBLE_BASE_URL is required when using "
                "'openai_compatible' provider"
            )
        if not model:
            raise ValueError(
                "OPENAI_COMPATIBLE_MODEL is required when using "
                "'openai_compatible' provider"
            )

        logger.info(
            "Initializing OpenAI-compatible LLM: %s at %s (max_tokens=%s)",
            model,
            base_url,
            settings.LLM_MAX_OUTPUT_TOKENS,
        )
        return OpenAICompatibleChatModel(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=0.1,
            max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
            timeout=timeout,
            enable_thinking=enable_thinking,
        )

    else:
        raise ValueError(
            f"Unsupported LLM provider: '{provider}'. "
            f"Supported: 'ollama', 'gemini', 'openai_compatible'"
        )
