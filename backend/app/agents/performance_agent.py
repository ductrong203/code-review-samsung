"""
Performance Agent — Specializes in detecting performance issues.

Covers: algorithm complexity, N+1 queries, memory leaks, resource management,
I/O bottlenecks, redundant computation.
"""
from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.agent_base import ReviewAgent, Category
from app.agents.agent_prompts import PERFORMANCE_SYSTEM_PROMPT, PERFORMANCE_REVIEW_PROMPT


class PerformanceAgent(ReviewAgent):
    """Agent specialized in finding performance issues."""

    def __init__(self, llm: BaseChatModel):
        super().__init__(
            llm=llm,
            category=Category.PERFORMANCE,
            name="⚡ Performance Agent",
        )

    def get_system_prompt(self) -> str:
        return PERFORMANCE_SYSTEM_PROMPT

    def get_review_prompt(self) -> str:
        return PERFORMANCE_REVIEW_PROMPT
