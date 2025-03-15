import os
import json
import faiss
import numpy as np
import logging
import openai
from openai import OpenAI

# Files for the FAISS index and ID mapping
INDEX_FILE = "./data/faiss_index.index"
MAPPING_FILE = "./data/id_mapping.json"
openai.api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI()

def get_embedding(text):

    try:
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text,
            encoding_format="float"
        )
        return response.data[0].embedding
    except Exception as e:
        logging.error(f"Failed to fetch embedding from OpenAI: {e}")
        return None


def update_faiss_index(text, article_id):
    """
    Computes an embedding for the given text and updates the FAISS index and ID mapping.
    If an index and mapping already exist, the new embedding is appended.
    """
    emb = get_embedding(text)
    if emb is None:
        logging.warning(f"Skipping FAISS update for article {article_id} due to embedding error.")
        return
    emb_np = np.array(emb).reshape(1, -1).astype("float32")
    
    # Load existing index and mapping if they exist
    if os.path.exists(INDEX_FILE) and os.path.exists(MAPPING_FILE):
        index = faiss.read_index(INDEX_FILE)
        with open(MAPPING_FILE, "r", encoding="utf-8") as f:
            mapping = json.load(f)
    else:
        dimension = emb_np.shape[1]
        index = faiss.IndexFlatL2(dimension)
        mapping = []
    
    # Only add the embedding if the article ID is not already in the mapping
    if article_id in mapping:
        logging.info(f"Article {article_id} already exists in the vector store.")
        return

    index.add(emb_np)
    mapping.append(article_id)

    # Save the updated index and mapping
    os.makedirs(os.path.dirname(INDEX_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(MAPPING_FILE), exist_ok=True)
    faiss.write_index(index, INDEX_FILE)
    with open(MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=4)
    logging.info(f"Updated FAISS index with article {article_id}. Total vectors: {index.ntotal}")