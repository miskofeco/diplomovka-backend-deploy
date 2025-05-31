import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text
from data.db import SessionLocal
from processing.vectorstore import get_embedding 

def find_similar_article(article_text, threshold=0.85):
    # Generate the embedding for the new article
    new_embedding = get_embedding(article_text)
    if new_embedding is None:
        return None

    with SessionLocal() as session:
        return extracted_articles(
            session, new_embedding, threshold
        )



def extracted_articles(session, new_embedding, threshold):
    # Fetch stored embeddings from database
    result = session.execute(text("SELECT id, summary, embedding FROM article_embeddings"))
    stored_articles = result.fetchall()

    most_similar = None
    highest_similarity = 0

    # Compare with stored embeddings
    for article_id, summary, stored_embedding in stored_articles:
        stored_embedding = np.array(stored_embedding)
        similarity = np.dot(new_embedding, stored_embedding) / (np.linalg.norm(new_embedding) * np.linalg.norm(stored_embedding))

        if similarity > highest_similarity:
            highest_similarity = similarity
            most_similar = {"id": article_id, "summary": summary}

    # Return most similar article if above threshold
    return most_similar if highest_similarity >= threshold else None