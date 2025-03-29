from flask import Flask, request, jsonify
from flask_cors import CORS
from scraping.scraping import scrape_for_new_articles
from data.db import SessionLocal
from sqlalchemy import text

from data.db import engine
from sqlalchemy import text

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, ARRAY, REAL

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
    # embedding as a vector, array, or JSON—whatever suits your setup
    embedding = Column(ARRAY(REAL))
    
class ProcessedURL(Base):
    __tablename__ = "processed_urls"
    url = Column(String, primary_key=True)
    scraped_at = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

app = Flask(__name__)
CORS(app)  # povolí prístup z frontendu

@app.route("/api/articles", methods=["GET"])
def get_articles():
    session = SessionLocal()
    result = session.execute(
        text("SELECT title, intro, summary, url, category, tags, top_image, scraped_at FROM articles ORDER BY id DESC")
    )
    articles = [{
        "title": r[0],
        "intro": r[1],
        "summary": r[2],
        "url": r[3],
        "category": r[4],
        "tags": r[5],
        "top_image": r[6],
        "scraped_at": r[7],
    } for r in result.fetchall()]
    return jsonify(articles)

@app.route("/api/scrape", methods=["POST"])
def scrape_articles():
    scrape_for_new_articles()
    return jsonify({"message": "Scraping completed"})

if __name__ == "__main__":
    import os
    Base.metadata.create_all(engine)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)