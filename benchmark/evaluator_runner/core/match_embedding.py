"""
Embedding Semantic Matching Module

Uses local Ollama embedding model to compare code review comments.
"""
import os
import json
import math
from pathlib import Path
from dotenv import load_dotenv
import aiohttp
from evaluator_runner.core.match_base import SemanticMatchResult

# Load .env from benchmark directory
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)

class OllamaEmbeddingMatcher:
    """Ollama-based embedding semantic matcher (no API key required)"""

    def __init__(self):
        self.base_url = os.getenv('EMBEDDING_MODEL_URL', 'http://localhost:11434/api')
        self.model = os.getenv('EMBEDDING_MODEL', 'nomic-embed-text')
        self.similarity_threshold = 0.7  # Threshold for determining similarity

    async def _get_embedding(self, text: str) -> list:
        """Get embedding from Ollama for a given text"""
        url = f"{self.base_url}/embed"
        payload = {
            "model": self.model,
            "input": text
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('embeddings', [[]])[0]
                    else:
                        raise Exception(f"Ollama API error: {resp.status}")
        except Exception as e:
            raise Exception(f"Failed to get embedding from Ollama: {str(e)}")

    def _cosine_similarity(self, vec1: list, vec2: list) -> float:
        """Calculate cosine similarity between two vectors"""
        if not vec1 or not vec2:
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)

    async def match(self, comment1: str, comment2: str) -> SemanticMatchResult:
        """
        Compare two comments using embedding similarity.
        
        Args:
            comment1: First comment
            comment2: Second comment
            
        Returns:
            SemanticMatchResult with similarity assessment
        """
        try:
            # Get embeddings for both comments
            embed1 = await self._get_embedding(comment1)
            embed2 = await self._get_embedding(comment2)
            
            # Calculate cosine similarity
            similarity = self._cosine_similarity(embed1, embed2)
            
            # Determine if similar based on threshold
            is_similar = similarity >= self.similarity_threshold
            
            reason = f"Embedding similarity: {similarity:.3f} (threshold: {self.similarity_threshold})"
            
            return SemanticMatchResult(
                is_similar=is_similar,
                reason=reason,
                raw_response=f"similarity_score={similarity:.3f}"
            )
        except Exception as e:
            # If embedding fails, return false with error reason
            return SemanticMatchResult(
                is_similar=False,
                reason=f"Embedding error: {str(e)}",
                raw_response=str(e)
            )

_matcher_instance = None

def _get_matcher() -> OllamaEmbeddingMatcher:
    """Get matcher singleton"""
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = OllamaEmbeddingMatcher()
    return _matcher_instance

async def match_embedding(str1: str, str2: str) -> dict:
    """
    Compare two comments using local Ollama embedding model.

    Args:
        str1: First comment
        str2: Second comment

    Returns:
        Dict containing is_similar, reason, raw_response
    """
    matcher = _get_matcher()
    result = await matcher.match(str1, str2)
    return result.to_dict()