from flask import Flask, request, jsonify
from flask_cors import CORS
from sqlalchemy import text, Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, ARRAY, REAL
from sqlalchemy.ext.declarative import declarative_base
import numpy as np
from openai import OpenAI
import os
import logging

# Add OpenAI client for embeddings
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_embedding(text: str) -> list:
    """Generate embedding for text using OpenAI"""
    try:
        response = openai_client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        logging.error(f"Error generating embedding: {e}")
        return None

def cosine_similarity(a, b):
    """Calculate cosine similarity between two vectors"""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# Importuj svoje moduly
from scraping.scraping import scrape_for_new_articles
from data.db import SessionLocal, engine # Uisti sa, že engine je tu správne importovaný/definovaný

# Definícia modelov
Base = declarative_base()

class Article(Base):
    __tablename__ = 'articles'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    url = Column(ARRAY(String), nullable=False)
    title = Column(String)
    intro = Column(Text)
    summary = Column(Text)
    category = Column(String)
    tags = Column(ARRAY(String), nullable=True)
    top_image = Column(String)
    scraped_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

class ArticleEmbedding(Base):
    __tablename__ = "article_embeddings"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    summary = Column(Text)
    embedding = Column(ARRAY(REAL))

class ProcessedURL(Base):
    __tablename__ = "processed_urls"
    url = Column(String, primary_key=True)
    scraped_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

# --- Inicializácia Flask aplikácie ---
app = Flask(__name__)
CORS(app)  # povolí prístup z frontendu

# --- Vytvorenie tabuliek (ak neexistujú) PRED prvou požiadavkou ---
# Toto sa vykoná, keď Gunicorn importuje 'app'
# Uisti sa, že 'engine' je už definovaný a nakonfigurovaný s DATABASE_URL
try:
    print("Attempting to create database tables if they don't exist...")
    # Je dobré to dať do kontextu aplikácie, aj keď pre create_all to nemusí byť nutné
    with app.app_context():
         # Tu sa vytvoria VŠETKY tabuľky (articles, article_embeddings, processed_urls)
         # ktoré sú definované pomocou Base a ešte v databáze neexistujú.
         Base.metadata.create_all(bind=engine)
    print("Database tables check/creation complete.")
except Exception as e:
    print(f"An error occurred during table creation: {e}")
    # Zváž, či tu aplikáciu ukončiť, alebo len zalogovať chybu

# --- Definície API endpointov ---
@app.route("/api/articles", methods=["GET"])
def get_articles():
    session = SessionLocal()
    try:
        # Get pagination parameters
        limit = request.args.get('limit', type=int)
        offset = request.args.get('offset', type=int)
        
        # Build the SQL query with pagination - INCLUDE ID FIELD
        query = """
            SELECT 
                id, title, intro, summary, url, category, tags, top_image, scraped_at
            FROM articles 
            ORDER BY scraped_at DESC
        """
        
        # Add LIMIT and OFFSET if provided
        params = {}
        if limit is not None:
            query += " LIMIT :limit"
            params['limit'] = limit
        if offset is not None:
            query += " OFFSET :offset"
            params['offset'] = offset
            
        result = session.execute(text(query), params)
        
        articles = [{
            "id": str(r[0]) if r[0] else None,  # Add ID field
            "title": r[1],
            "intro": r[2],
            "summary": r[3],
            "url": r[4],
            "category": r[5],
            "tags": r[6],
            "top_image": r[7],
            "scraped_at": r[8].isoformat() if r[8] else None
        } for r in result.fetchall()]

        return jsonify(articles)
    except Exception as e:
        session.rollback()
        print(f"Error fetching articles: {e}")
        return jsonify({"error": "Could not fetch articles", "details": str(e)}), 500
    finally:
        session.close()

@app.route("/api/scrape", methods=["POST"])
def scrape_articles():
    try:
        data = request.get_json()
        max_articles_per_page = data.get('max_articles_per_page', 3)  # Default to 3 per page
        max_total_articles = data.get('max_total_articles', None)  # Optional total limit
        
        # Spustenie scrapingu s limitom
        scrape_for_new_articles(
            max_articles_per_page=max_articles_per_page,
            max_total_articles=max_total_articles
        )
        
        return jsonify({
            "message": f"Scraping task started for {max_articles_per_page} articles per page" + 
                      (f" (max total: {max_total_articles})" if max_total_articles else "")
        })
    except Exception as e:
        print(f"Error during scraping: {e}")  # Logovanie chyby
        return jsonify({"error": "Scraping failed", "details": str(e)}), 500

# Pridajme endpoint pre vyhľadávanie článkov
@app.route("/api/articles/search", methods=["GET"])
def search_articles():
    session = SessionLocal()
    try:
        query = request.args.get('q', '')
        advanced = request.args.get('advanced', 'false').lower() == 'true'
        
        if not query or len(query) < 2:
            return jsonify([])
        
        if advanced:
            # Vector similarity search
            logging.info(f"Performing advanced vector search for: {query}")
            
            # Generate embedding for the search query
            query_embedding = get_embedding(query)
            if not query_embedding:
                return jsonify({"error": "Failed to generate query embedding"}), 500
            
            # Check if we have any embeddings first
            embeddings_count = session.execute(text("SELECT COUNT(*) FROM article_embeddings WHERE embedding IS NOT NULL")).scalar()
            logging.info(f"Found {embeddings_count} articles with embeddings")
            
            if embeddings_count == 0:
                logging.warning("No embeddings found, falling back to regular search")
                # Fall back to regular search if no embeddings
                advanced = False
            else:
                # Get all article embeddings with proper JOIN
                embeddings_query = """
                    SELECT 
                        a.id, a.title, a.intro, a.summary, a.url, a.category, a.tags, a.top_image, a.scraped_at,
                        ae.embedding
                    FROM articles a
                    INNER JOIN article_embeddings ae ON a.id = ae.id
                    WHERE ae.embedding IS NOT NULL
                """
                
                result = session.execute(text(embeddings_query))
                
                articles_with_similarity = []
                processed_count = 0
                
                for r in result:
                    stored_embedding = r[9]  # The embedding array
                    if stored_embedding and len(stored_embedding) > 0:
                        try:
                            # Calculate similarity
                            similarity = cosine_similarity(query_embedding, stored_embedding)
                            processed_count += 1
                            
                            # threshold for better results
                            if similarity > 0.8: 
                                articles_with_similarity.append({
                                    "similarity": float(similarity),
                                    "id": str(r[0]) if r[0] else None,
                                    "title": r[1],
                                    "intro": r[2],
                                    "summary": r[3],
                                    "url": r[4],
                                    "category": r[5],
                                    "tags": r[6],
                                    "top_image": r[7],
                                    "scraped_at": r[8].isoformat() if r[8] else None
                                })
                        except Exception as e:
                            logging.warning(f"Error calculating similarity for article {r[0]}: {e}")
                            continue
                
                logging.info(f"Processed {processed_count} embeddings, found {len(articles_with_similarity)} similar articles")
                
                if len(articles_with_similarity) == 0:
                    logging.warning("No similar articles found with vector search, falling back to regular search")
                    advanced = False
                else:
                    # Sort by similarity score (highest first)
                    articles_with_similarity.sort(key=lambda x: x['similarity'], reverse=True)
                    
                    # Remove similarity score from final results and limit to 20
                    articles = []
                    seen_titles = set()
                    
                    for article in articles_with_similarity[:20]:
                        title = article['title']
                        if title not in seen_titles:
                            seen_titles.add(title)
                            # Remove similarity score from the final result
                            del article['similarity']
                            articles.append(article)
                    
                    logging.info(f"Vector search returned {len(articles)} results")
                    return jsonify(articles)
        
        if not advanced:
            # Regular text search (existing functionality)
            logging.info(f"Performing regular text search for: {query}")
            search_query = f"%{query.lower()}%"
            
            sql_query = """
                SELECT DISTINCT
                    id, title, intro, summary, url, category, tags, top_image, scraped_at
                FROM articles 
                WHERE 
                    LOWER(title) LIKE :query OR
                    LOWER(summary) LIKE :query OR
                    LOWER(intro) LIKE :query OR
                    LOWER(category) LIKE :query OR
                    tags::text LIKE :query
                ORDER BY scraped_at DESC
                LIMIT 20
            """
                
            result = session.execute(text(sql_query), {"query": search_query})
            
            articles = []
            seen_titles = set()
            
            for r in result:
                title = r[1]
                if title not in seen_titles:
                    seen_titles.add(title)
                    articles.append({
                        "id": str(r[0]) if r[0] else None,
                        "title": title,
                        "intro": r[2],
                        "summary": r[3],
                        "url": r[4],
                        "category": r[5],
                        "tags": r[6],
                        "top_image": r[7],
                        "scraped_at": r[8].isoformat() if r[8] else None
                    })
            
            logging.info(f"Regular search returned {len(articles)} results")
            return jsonify(articles)
        
    except Exception as e:
        logging.error(f"Error searching articles: {str(e)}")
        return jsonify({"error": "Search failed"}), 500
    finally:
        session.close()

@app.route("/api/articles/<article_id>/similar", methods=["GET"])
def get_similar_articles(article_id):
    """Get semantically similar articles using vector embeddings - focuses purely on relevance"""
    session = SessionLocal()
    try:
        logging.info(f"Starting fresh similarity search for article {article_id}")
        
        # Get the current article and its embedding
        current_article_query = """
            SELECT a.id, a.title, a.summary, ae.embedding
            FROM articles a
            LEFT JOIN article_embeddings ae ON a.id = ae.id
            WHERE a.id = :article_id
        """
        
        current_result = session.execute(text(current_article_query), {"article_id": article_id}).fetchone()
        
        if not current_result:
            logging.error(f"Article {article_id} not found")
            return jsonify({"error": "Article not found"}), 404
        
        current_embedding = current_result[3]
        current_title = current_result[1]
        
        logging.info(f"Processing article: {current_title[:50]}...")
        
        if not current_embedding:
            # Generate embedding for this article if missing
            logging.warning(f"No embedding found for article {article_id}, generating fresh embedding")
            
            current_summary = current_result[2]
            if current_summary:
                fresh_embedding = get_embedding(current_summary)
                if fresh_embedding:
                    # Store the new embedding for future use
                    try:
                        from processing.vectorstore import store_embedding
                        store_embedding(article_id, current_summary)
                        current_embedding = fresh_embedding
                        logging.info(f"Generated and stored new embedding for article {article_id}")
                    except Exception as e:
                        logging.warning(f"Could not store embedding: {e}")
                        current_embedding = fresh_embedding
            
            # If still no embedding, fallback to recent diverse articles
            if not current_embedding:
                logging.warning(f"Could not generate embedding for article {article_id}, using recent articles fallback")
                
                recent_query = """
                    SELECT DISTINCT
                        a.id, a.title, a.intro, a.summary, a.url, a.category, a.tags, a.top_image, a.scraped_at
                    FROM articles a
                    WHERE a.id != :article_id
                    ORDER BY a.scraped_at DESC
                    LIMIT 10
                """
                
                result = session.execute(text(recent_query), {"article_id": article_id})
                
                articles = []
                for r in result:
                    articles.append({
                        "id": str(r[0]) if r[0] else None,
                        "title": r[1],
                        "intro": r[2],
                        "summary": r[3],
                        "url": r[4],
                        "category": r[5],
                        "tags": r[6],
                        "top_image": r[7],
                        "scraped_at": r[8].isoformat() if r[8] else None
                    })
                
                logging.info(f"Fallback: returning {len(articles)} recent articles")
                return jsonify(articles)
        
        # Perform fresh similarity search across ALL articles
        logging.info(f"Performing fresh semantic similarity search across all articles")
        
        similarity_query = """
            SELECT 
                a.id, a.title, a.intro, a.summary, a.url, a.category, a.tags, a.top_image, a.scraped_at,
                ae.embedding
            FROM articles a
            INNER JOIN article_embeddings ae ON a.id = ae.id
            WHERE a.id != :article_id AND ae.embedding IS NOT NULL
            ORDER BY a.scraped_at DESC
        """
        
        result = session.execute(text(similarity_query), {"article_id": article_id})
        
        articles_with_similarity = []
        processed_count = 0
        similarity_scores = []
        
        for r in result:
            stored_embedding = r[9]  # The embedding array
            if stored_embedding and len(stored_embedding) > 0:
                try:
                    # Calculate similarity
                    similarity = cosine_similarity(current_embedding, stored_embedding)
                    processed_count += 1
                    similarity_scores.append(similarity)
                    
                    # Use adaptive threshold - lower for better coverage
                    if similarity > 0.1:  # Very low threshold to capture diverse articles
                        articles_with_similarity.append({
                            "similarity": float(similarity),
                            "id": str(r[0]) if r[0] else None,
                            "title": r[1],
                            "intro": r[2],
                            "summary": r[3],
                            "url": r[4],
                            "category": r[5],
                            "tags": r[6],
                            "top_image": r[7],
                            "scraped_at": r[8].isoformat() if r[8] else None
                        })
                        
                except Exception as e:
                    logging.warning(f"Error calculating similarity for article {r[0]}: {e}")
                    continue
        
        # Log search statistics
        if similarity_scores:
            avg_similarity = sum(similarity_scores) / len(similarity_scores)
            max_similarity = max(similarity_scores)
            logging.info(f"Similarity stats: processed={processed_count}, found={len(articles_with_similarity)}, avg={avg_similarity:.3f}, max={max_similarity:.3f}")
        
        # If no similar articles found with low threshold, use even lower threshold or fallback
        if len(articles_with_similarity) == 0:
            logging.warning("No articles found with similarity > 0.1, trying with very low threshold")
            
            # Try with even lower threshold
            articles_with_similarity = []
            result = session.execute(text(similarity_query), {"article_id": article_id})
            
            for r in result:
                stored_embedding = r[9]
                if stored_embedding and len(stored_embedding) > 0:
                    try:
                        similarity = cosine_similarity(current_embedding, stored_embedding)
                        if similarity > 0.05:  # Very low threshold
                            articles_with_similarity.append({
                                "similarity": float(similarity),
                                "id": str(r[0]) if r[0] else None,
                                "title": r[1],
                                "intro": r[2],
                                "summary": r[3],
                                "url": r[4],
                                "category": r[5],
                                "tags": r[6],
                                "top_image": r[7],
                                "scraped_at": r[8].isoformat() if r[8] else None
                            })
                    except Exception as e:
                        continue
            
            # If still nothing, fallback to recent articles
            if len(articles_with_similarity) == 0:
                logging.warning("No similar articles found even with very low threshold, using recent articles")
                
                recent_query = """
                    SELECT DISTINCT
                        a.id, a.title, a.intro, a.summary, a.url, a.category, a.tags, a.top_image, a.scraped_at
                    FROM articles a
                    WHERE a.id != :article_id
                    ORDER BY a.scraped_at DESC
                    LIMIT 10
                """
                
                result = session.execute(text(recent_query), {"article_id": article_id})
                
                articles = []
                for r in result:
                    articles.append({
                        "id": str(r[0]) if r[0] else None,
                        "title": r[1],
                        "intro": r[2],
                        "summary": r[3],
                        "url": r[4],
                        "category": r[5],
                        "tags": r[6],
                        "top_image": r[7],
                        "scraped_at": r[8].isoformat() if r[8] else None
                    })
                
                logging.info(f"Final fallback: returning {len(articles)} recent articles")
                return jsonify(articles)
        
        # Sort by similarity score (highest first) - PURE RELEVANCE-BASED SELECTION
        articles_with_similarity.sort(key=lambda x: x['similarity'], reverse=True)
        
        # Log top similarity matches
        logging.info("Top 10 similarity matches:")
        for i, article in enumerate(articles_with_similarity[:10]):
            logging.info(f"  {i+1}. similarity={article['similarity']:.3f}, category={article['category']}, title={article['title'][:50]}...")
        
        # Simply take the top 10 most similar articles - no category constraints
        final_articles = articles_with_similarity[:10]
        
        # Remove similarity scores from final results
        articles = []
        for article in final_articles:
            if 'similarity' in article:
                del article['similarity']
            articles.append(article)
        
        # Log final results
        categories_used = set(article['category'] for article in articles)
        logging.info(f"Final results: {len(articles)} articles from {len(categories_used)} categories: {sorted(categories_used)}")
        logging.info(f"Selected articles purely based on similarity scores")
        
        return jsonify(articles)
        
    except Exception as e:
        logging.error(f"Error finding similar articles for {article_id}: {str(e)}", exc_info=True)
        
        # Emergency fallback - return recent articles
        try:
            emergency_query = """
                SELECT DISTINCT
                    a.id, a.title, a.intro, a.summary, a.url, a.category, a.tags, a.top_image, a.scraped_at
                FROM articles a
                WHERE a.id != :article_id
                ORDER BY a.scraped_at DESC
                LIMIT 8
            """
            
            result = session.execute(text(emergency_query), {"article_id": article_id})
            
            articles = []
            for r in result:
                articles.append({
                    "id": str(r[0]) if r[0] else None,
                    "title": r[1],
                    "intro": r[2],
                    "summary": r[3],
                    "url": r[4],
                    "category": r[5],
                    "tags": r[6],
                    "top_image": r[7],
                    "scraped_at": r[8].isoformat() if r[8] else None
                })
            
            logging.info(f"Emergency fallback: returning {len(articles)} recent articles")
            return jsonify(articles)
            
        except Exception as emergency_error:
            logging.error(f"Emergency fallback also failed: {emergency_error}")
            return jsonify({"error": "Failed to find similar articles"}), 500
    finally:
        session.close()

@app.route("/api/articles/<article_slug>/details", methods=["GET"])
def get_article_details(article_slug):
    """Get article details by slug for debugging"""
    session = SessionLocal()
    try:
        # Try to find article by title matching the slug
        query = """
            SELECT id, title, intro, summary, url, category, tags, top_image, scraped_at
            FROM articles 
            WHERE LOWER(REPLACE(REPLACE(REPLACE(title, ' ', '-'), '.', ''), ',', '')) LIKE :slug
            LIMIT 1
        """
        
        # Convert slug back to searchable format
        slug_pattern = f"%{article_slug.replace('-', '%')}%"
        
        result = session.execute(text(query), {"slug": slug_pattern}).fetchone()
        
        if not result:
            logging.warning(f"Article not found for slug: {article_slug}")
            return jsonify({"error": "Article not found"}), 404
        
        article = {
            "id": str(result[0]) if result[0] else None,
            "title": result[1],
            "intro": result[2],
            "summary": result[3],
            "url": result[4],
            "category": result[5],
            "tags": result[6],
            "top_image": result[7],
            "scraped_at": result[8].isoformat() if result[8] else None,
            "slug": article_slug
        }
        
        logging.info(f"Found article: ID={article['id']}, Title={article['title'][:50]}...")
        return jsonify(article)
        
    except Exception as e:
        logging.error(f"Error getting article details: {str(e)}")
        return jsonify({"error": "Failed to get article details"}), 500
    finally:
        session.close()

# --- Tento blok sa na Render s Gunicornom nespustí ---
if __name__ == "__main__":
    import os
    # Lokálne spustenie pre vývoj
    print("Running in local development mode...")
    # Lokálne môžeš tiež vytvárať tabuľky, ale už by mali byť vytvorené vyššie
    # with app.app_context():
    #     Base.metadata.create_all(engine)
    port = int(os.environ.get("PORT", 5001)) # Použi iný port lokálne, napr. 5001
    app.run(host="0.0.0.0", port=port, debug=True) # Zapni debug pre lokálny vývoj
