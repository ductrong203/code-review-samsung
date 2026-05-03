"""
Maintainability Agent — Specializes in detecting maintainability and readability issues.

Covers: SOLID violations, code duplication, naming clarity, error handling,
structural design, documentation, testability.
"""
from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.agent_base import ReviewAgent, Category
from app.agents.agent_prompts import (
    MAINTAINABILITY_SYSTEM_PROMPT,
    MAINTAINABILITY_REVIEW_PROMPT,
)


class MaintainabilityAgent(ReviewAgent):
    """Agent specialized in finding maintainability and readability issues."""

    def __init__(self, llm: BaseChatModel):
        super().__init__(
            llm=llm,
            category=Category.MAINTAINABILITY,
            name="📖 Maintainability Agent",
        )

    def get_system_prompt(self) -> str:
        return MAINTAINABILITY_SYSTEM_PROMPT

    def get_review_prompt(self) -> str:
        return MAINTAINABILITY_REVIEW_PROMPT
