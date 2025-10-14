import logging
import os
from typing import List, Optional

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_api_key = os.getenv("OPENAI_API_KEY")
_openai_client: Optional[OpenAI] = None

if _api_key:
    _openai_client = OpenAI(api_key=_api_key)
else:
    logging.warning("OPENAI_API_KEY not configured; embedding generation will be disabled.")


def get_embedding(text: str) -> Optional[List[float]]:
    """Generate embeddings for the supplied text using OpenAI."""
    if not _openai_client:
        logging.error("Embedding requested but OpenAI client is not initialized.")
        return None

    try:
        response = _openai_client.embeddings.create(
            model="text-embedding-ada-002",
            input=text,
        )
        return response.data[0].embedding
    except Exception as exc:
        logging.error("Error generating embedding: %s", exc)
        return None


def cosine_similarity(vector_a: List[float], vector_b: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(vector_a)
    b = np.array(vector_b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


__all__ = ["get_embedding", "cosine_similarity"]
