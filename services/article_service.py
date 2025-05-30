from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from models.article import ArticleInDB, ArticleCreate, Article
from typing import List, Optional

def search_articles(db: Session, query: str, limit: int = 10) -> List[ArticleInDB]:
    """
    Search articles by query string.
    The search is performed on title, content, intro, category, and tags.
    """
    # Normalize query
    search_query = f"%{query.lower()}%"
    
    # Search in multiple fields
    articles = db.query(ArticleInDB).filter(
        or_(
            func.lower(ArticleInDB.title).like(search_query),
            func.lower(ArticleInDB.content).like(search_query),
            func.lower(ArticleInDB.intro).like(search_query),
            func.lower(ArticleInDB.category).like(search_query),
            # Search in tags (this is more complex as tags is an array)
            ArticleInDB.tags.cast(str).like(search_query)
        )
    ).order_by(ArticleInDB.scraped_at.desc()).limit(limit).all()
    
    return articles