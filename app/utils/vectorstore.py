import logging
import os

import numpy as np
import tiktoken
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import text as tx

from data.db import SessionLocal

load_dotenv()

if api_key := os.getenv("OPENAI_API_KEY"):
    client = OpenAI(api_key=api_key)
else:
    raise ValueError("Missing OPENAI_API_KEY. Ensure it's set in .env or environment variables.")

EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
MAX_TOKENS_PER_CHUNK = int(os.getenv("EMBEDDING_MAX_TOKENS", "7500"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("EMBEDDING_CHUNK_OVERLAP", "200"))
_encoding = tiktoken.get_encoding("cl100k_base")


def _chunk_text(text: str) -> list[str]:
    tokens = _encoding.encode(text)
    if len(tokens) <= MAX_TOKENS_PER_CHUNK:
        return [text]

    chunks = []
    start = 0
    step = max(1, MAX_TOKENS_PER_CHUNK - CHUNK_OVERLAP_TOKENS)

    while start < len(tokens):
        end = min(len(tokens), start + MAX_TOKENS_PER_CHUNK)
        chunk_tokens = tokens[start:end]
        chunks.append(_encoding.decode(chunk_tokens))
        if end == len(tokens):
            break
        start += step

    return chunks


def get_embedding(text: str):
    if not text:
        logging.warning("Empty text supplied for embedding; returning None.")
        return None

    try:
        chunks = _chunk_text(text)
        embeddings = []

        for chunk in chunks:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=chunk
            )
            embeddings.append(np.array(response.data[0].embedding, dtype=np.float32))

        if not embeddings:
            logging.error("No embeddings returned from OpenAI.")
            return None

        if len(embeddings) == 1:
            return embeddings[0].tolist()

        # Average pool chunk embeddings to a single vector
        aggregated = np.mean(np.stack(embeddings), axis=0)
        return aggregated.tolist()
    except Exception as e:
        logging.error(f"Failed to fetch embedding from OpenAI: {e}")
        return None

def store_embedding(article_id, text):
    """Generates and stores an embedding in PostgreSQL (pgvector)."""
    session = SessionLocal()
    emb = get_embedding(text)
    
    if emb is None:
        logging.warning(f"Skipping embedding for article {article_id} due to error.")
        return

    emb_np = np.array(emb, dtype=np.float32).tolist()  # Convert NumPy array to list

    session.execute(
        tx("INSERT INTO article_embeddings (id, embedding, summary) VALUES (:id, :embedding, :summary) "
            "ON CONFLICT (id) DO UPDATE SET embedding = :embedding"),
        {
            "id": article_id, 
            "embedding": emb_np,
            "summary": text
        }
    )

    session.commit()
    session.close()
    logging.info(f"Stored embedding for article {article_id}.")
