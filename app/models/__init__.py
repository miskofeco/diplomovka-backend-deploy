from sqlalchemy import Column, DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSON, REAL, UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Article(Base):
    __tablename__ = "articles"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    url = Column(ARRAY(String), nullable=False)
    title = Column(String)
    intro = Column(Text)
    summary = Column(Text)
    category = Column(String)
    tags = Column(ARRAY(String), nullable=True)
    top_image = Column(String)
    scraped_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    fact_check_results = Column(JSON)
    summary_annotations = Column(JSON)


class ArticleEmbedding(Base):
    __tablename__ = "article_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    summary = Column(Text)
    embedding = Column(ARRAY(REAL))


class ProcessedURL(Base):
    __tablename__ = "processed_urls"

    url = Column(String, primary_key=True)
    scraped_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    orientation = Column(String, default="neutral")
    confidence = Column(REAL, default=0.0)
    reasoning = Column(Text)


__all__ = ["Base", "Article", "ArticleEmbedding", "ProcessedURL"]
