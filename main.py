# backend/main.py
import logging
from pipeline import process_new_articles
from data.db import engine
from sqlalchemy import text


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY, REAL

Base = declarative_base()

class Article(Base):
    __tablename__ = 'articles'
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    url = Column(String, unique=True, nullable=False)
    title = Column(String)
    intro = Column(Text)
    summary = Column(Text)
    category = Column(String)
    tags = Column(Text)  # or postgresql.JSON, etc.
    top_image = Column(String)
    
class ArticleEmbedding(Base):
    __tablename__ = "article_embeddings"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    # embedding as a vector, array, or JSON—whatever suits your setup
    embedding = Column(ARRAY(REAL))

def main():
    # Run the full pipeline: scrape new articles, process them with LLM,
    # update the vectorstore, and append the results to processed.json.
    # Suppose you have engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    process_new_articles()

if __name__ == "__main__":
    main()