import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text
from data.db import SessionLocal
from processing.vectorstore import get_embedding 

def find_similar_article(article_text, threshold=0.9):
    # Generate the embedding for the new article
    new_embedding = get_embedding(article_text)
    if new_embedding is None:
        return None

    with SessionLocal() as session:
        return extracted_articles(
            session, new_embedding, threshold
        )



def extracted_articles(session, new_embedding, threshold):
    most_similar = None
    highest_similarity = 0.0 # Inicializuj ako float

    try:
        # Priprav nový embedding ako numpy pole
        np_new_embedding = np.array(new_embedding, dtype=np.float32)
        norm_new = np.linalg.norm(np_new_embedding)

        # Načítaj uložené embeddingy
        result = session.execute(text("SELECT id, summary, embedding FROM article_embeddings"))
        stored_articles = result.fetchall()
        print(f"Debug: Found {len(stored_articles)} stored articles to compare against.") # Log

        if not stored_articles:
            print("Debug: No stored articles found, skipping similarity comparison.")
            return None # Ak nie sú uložené články, niet s čím porovnávať

        # Porovnaj s uloženými embeddingami
        for article_id, summary, stored_embedding_db in stored_articles:
            try:
                # --- Vynútená konverzia uloženého embeddingu ---
                np_stored_embedding = np.array(stored_embedding_db, dtype=np.float32)
                norm_stored = np.linalg.norm(np_stored_embedding)

                # Ošetrenie delenia nulou
                if norm_new > 0 and norm_stored > 0:
                    similarity = np.dot(np_new_embedding, np_stored_embedding) / (norm_new * norm_stored)
                else:
                    similarity = 0.0

                # Aktualizuj najpodobnejší článok
                if similarity > highest_similarity:
                    highest_similarity = similarity
                    most_similar = {"id": article_id, "summary": summary}
                    # print(f"Debug: New highest similarity {highest_similarity} with article {article_id}") # Voliteľný debug výpis

            except ValueError as ve:
                print(f"!!! WARNING: Could not convert stored embedding for article {article_id} to float array. Skipping this comparison.")
                print(f"    Error: {ve}")
                print(f"    Problematic stored_embedding type: {type(stored_embedding_db)}, snippet: {str(stored_embedding_db)[:100]}...")
                continue # Pokračuj ďalším uloženým článkom
            except Exception as inner_e:
                print(f"!!! WARNING: Unexpected error during similarity calculation for article {article_id}. Skipping.")
                continue

        # Vráť najpodobnejší článok, ak prekročil prah
        if most_similar:
             print(f"Debug: Highest similarity found: {highest_similarity}. Threshold: {threshold}")
             return most_similar if highest_similarity >= threshold else None
        else:
             print("Debug: No similar article found above the threshold.")
             return None

    except ValueError as ve:
         # Chyba pri konverzii np_new_embedding
         print(f"    Error: {ve}")
         print(f"    Problematic new_embedding type: {type(new_embedding)}, snippet: {str(new_embedding)[:100]}...")
         return None # Vráť None, ak sa nový embedding nedá spracovať
    except Exception as outer_e:
         return None # Vráť None pri neočakávanej chybe