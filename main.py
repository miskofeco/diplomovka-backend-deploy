# backend/main.py
import logging
from pipeline import process_new_articles

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def main():
    # Run the full pipeline: scrape new articles, process them with LLM,
    # update the vectorstore, and append the results to processed.json.
    process_new_articles()

if __name__ == "__main__":
    main()