"""
Defect Agent — Specializes in detecting code defects, bugs, and logic errors.

Covers: logic errors, null safety, type issues, control flow bugs, edge cases,
state management problems, race conditions.
"""
from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.agent_base import ReviewAgent, Category
from app.agents.agent_prompts import DEFECT_SYSTEM_PROMPT, DEFECT_REVIEW_PROMPT


class DefectAgent(ReviewAgent):
    """Agent specialized in finding code defects and bugs."""

    def __init__(self, llm: BaseChatModel):
        super().__init__(
            llm=llm,
            category=Category.CODE_DEFECT,
            name="🐛 Defect Agent",
        )

    def get_system_prompt(self) -> str:
        return DEFECT_SYSTEM_PROMPT

    def get_review_prompt(self) -> str:
        return DEFECT_REVIEW_PROMPT
