"""
Semantic Matcher Factory

Creates semantic matchers based on configuration.
"""
from typing import Callable, Awaitable, Dict, Any

from evaluator_runner.utils.config import SemanticMatcherType

# Type alias for semantic match function signature
SemanticMatchFunc = Callable[[str, str], Awaitable[Dict[str, Any]]]


def get_semantic_matcher(matcher_type: SemanticMatcherType) -> SemanticMatchFunc:
    """Get semantic matching function by type (lazy import to avoid unused deps)."""
    if matcher_type == SemanticMatcherType.LLM:
        from evaluator_runner.core.match_llm import match_llm

        return match_llm

    if matcher_type == SemanticMatcherType.EMBEDDING:
        from evaluator_runner.core.match_embedding import match_embedding

        return match_embedding

    raise ValueError(f"Unknown semantic matcher type: {matcher_type}")