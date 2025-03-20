import logging
from scraping.scraping import scrape_for_new_articles
from data.db import engine
from sqlalchemy import text


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
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

def main():
    Base.metadata.create_all(engine)
    scrape_for_new_articles()

if __name__ == "__main__":
    main()