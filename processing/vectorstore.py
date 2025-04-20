import openai
import logging
import numpy as np
from openai import OpenAI
import os
from sqlalchemy.orm import Session
from data.db import SessionLocal
from sqlalchemy import text as tx
import os 
from dotenv import load_dotenv

load_dotenv()

if api_key := os.getenv("OPENAI_API_KEY"):
    client = OpenAI(api_key=api_key)
else:
    raise ValueError("Missing OPENAI_API_KEY. Ensure it's set in .env or environment variables.")

def get_embedding(text):

    try:
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return response.data[0].embedding
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
