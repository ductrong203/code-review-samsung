"""
Security Agent — Specializes in detecting security vulnerabilities.

Covers: OWASP Top 10, injection attacks, authentication issues,
cryptographic failures, access control, data exposure.
"""
from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.agent_base import ReviewAgent, Category
from app.agents.agent_prompts import SECURITY_SYSTEM_PROMPT, SECURITY_REVIEW_PROMPT


class SecurityAgent(ReviewAgent):
    """Agent specialized in finding security vulnerabilities."""

    def __init__(self, llm: BaseChatModel):
        super().__init__(
            llm=llm,
            category=Category.SECURITY,
            name="🔒 Security Agent",
        )

    def get_system_prompt(self) -> str:
        return SECURITY_SYSTEM_PROMPT

    def get_review_prompt(self) -> str:
        return SECURITY_REVIEW_PROMPT
