from pydantic import BaseModel, Field
from typing import List
import logging
import json
import openai
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL")
client = OpenAI()

PREDEFINED_CATEGORIES = ["Politika", "Ekonomika", "Šport", "Kultúra", "Technológie", "Zdravie", "Veda"]
PREDEFINED_TAGS = ["Trendy", "Aktualne", "18+", "Krimi", "Zaujimavosti", "Zivotne-styl", "Ostatne", "Zo sveta", "Domáce", "Slovensko", "Svet", "Európa", "Amerika", "Ázia", "Afrika", "Austrália", "Pre mladych", "Pre zeny","Pre studentov"]

# Pydantic model
class ProcessedArticle(BaseModel):
    title: str = Field(..., title="title", description="Názov článku")
    intro: str = Field(..., title="intro", description="Úvodný pútavý text článku pár slovami")
    summary: str = Field(..., title="summary", description="Prepis článku v neutrálnej reči so spracovaním všetkých informácií")
    category: str
    tags: List[str]

def process_article(article_text: str):
    system_message = "Si nápomocný asistent..."
    user_message = f"""
    Spracuj nasledujúci text článku a vráť výsledok v JSON formáte s nasledujúcimi kľúčmi:
    - "title": Pútavý názov článku.
    - "intro": Krátky úvod, pútavý text pár slovami.
    - "summary": Prepis článku do pútavého textu so spracovaním všetkých informácií.
    - "category": Urč kategóriu článku. Možnosti sú: {PREDEFINED_CATEGORIES}
    - "tags": Na základe obsahu pridaj 1 alebo viac tags k článku. Možnosti sú: {PREDEFINED_TAGS}

    Text článku:
    {article_text}

    Vráť len platný JSON bez akýchkoľvek komentárov alebo dodatočného textu.
    """
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.7,
        max_tokens=1000,
        response_format=ProcessedArticle
    )
    # Return the parsed Pydantic model (as a dict)
    return response.choices[0].message.parsed.model_dump()


def main():
    scraped_file = "../data/scraped.json"
    processed_file = "../data/processed.json"

    try:
        with open(scraped_file, "r", encoding="utf-8") as f:
            articles = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load scraped articles: {e}")
        return

    processed_articles = []
    for article in articles:
        text = article.get("text", "")
        if text.strip():
            logging.info(f"Processing article: {article.get('title', 'No Title')}")
            try:
                processed = process_article(text)
                article["processed_text"] = processed
            except Exception as e:
                logging.error(f"Error processing article: {e}")
                article["processed_text"] = {"error": str(e)}
        else:
            logging.info("Article text is empty, skipping processing.")
        processed_articles.append(article)

    try:
        with open(processed_file, "w", encoding="utf-8") as f:
            json.dump(processed_articles, f, ensure_ascii=False, indent=4)
        logging.info(f"Processed articles saved to {processed_file}")
    except Exception as e:
        logging.error(f"Failed to save processed articles: {e}")

if __name__ == "__main__":
    main()