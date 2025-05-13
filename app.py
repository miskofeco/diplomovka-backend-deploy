from flask import Flask, request, jsonify
from flask_cors import CORS
from sqlalchemy import text, Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, ARRAY, REAL
from sqlalchemy.ext.declarative import declarative_base

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
        
        # Build the SQL query with pagination
        query = """
            SELECT 
                title, intro, summary, url, category, tags, top_image, scraped_at
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
            "title": r[0],
            "intro": r[1],
            "summary": r[2],
            "url": r[3],
            "category": r[4],
            "tags": r[5],
            "top_image": r[6],
            "scraped_at": r[7].isoformat() if r[7] else None
        } for r in result.fetchall()]

        return jsonify(articles)
    except Exception as e:
        session.rollback()
        print(f"Error fetching articles: {e}")
        return jsonify({"error": "Could not fetch articles", "details": str(e)}), 500
    finally:
        session.close() # Vždy zatvor session

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
