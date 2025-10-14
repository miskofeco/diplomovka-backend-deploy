from app.models import Base
from data.db import engine
from app.utils.scraper import scrape_for_new_articles


def main():
    Base.metadata.create_all(engine)
    scrape_for_new_articles()


if __name__ == "__main__":
    main()
