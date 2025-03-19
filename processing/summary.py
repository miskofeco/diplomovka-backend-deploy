from pydantic import BaseModel, Field
from typing import List
import openai
from openai import OpenAI
import os
from dotenv import load_dotenv


load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL")
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

PREDEFINED_CATEGORIES = ["Politika", "Ekonomika", "Šport", "Kultúra", "Technológie", "Zdravie", "Veda"]
PREDEFINED_TAGS = ["Trendy", "Aktualne", "18+", "Krimi", "Zaujimavosti", "Zivotny-styl", "Ostatne", "Zo sveta", "Domáce", "Slovensko", "Svet", "Európa", "Amerika", "Ázia", "Afrika", "Austrália", "Pre mladych", "Pre zeny","Pre studentov"]

# Pydantic model
class ProcessedArticle(BaseModel):
    title: str = Field(..., title="title", description="Názov článku")
    intro: str = Field(..., title="intro", description="Úvodný pútavý text článku pár slovami")
    summary: str = Field(..., title="summary", description="Sumarizácia článku v neutrálnej reči so spracovaním všetkých informácií a s použitím formátovania")
    category: str
    tags: List[str]
    
class UpdatedArticle(BaseModel):
    intro: str = Field(..., title="intro", description="Úvodný pútavý text článku pár slovami")
    summary: str = Field(..., title="summary", description="Sumarizácia článku v neutrálnej reči so spracovaním všetkých informácií a s použitím formátovania")

def process_article(article_text: str):

    max_length = 2000  # adjust this limit as needed
    if len(article_text) > max_length:
        truncated_text = article_text[:max_length] + "..."
    else:
        truncated_text = article_text

    system_message = "Si profesionalny novinár, ktorý spracúvava články pre webovú publikáciu."
    user_message = f"""
    Spracuj nasledujúci text článku a vráť výsledok v JSON formáte s nasledujúcimi kľúčmi:
    - "title": Pútavý názov článku.
    - "intro": Krátky úvod, pútavý text pár slovami.
    - "summary": Sumarizacia článku do pútavého textu so spracovaním všetkých informácií.  Zahrň do neho aj formátovanie – odsadenie, odseky a vhodné riadkové zlomy, ktoré majú byť zachované.
    - "category": Urč kategóriu článku. Možnosti sú: {PREDEFINED_CATEGORIES}
    - "tags": Na základe obsahu pridaj 1 alebo viac tags k článku. Možnosti sú: {PREDEFINED_TAGS}

    Text článku:
    {truncated_text}

    Vráť len platný JSON bez akýchkoľvek komentárov alebo dodatočného textu.
    """
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.7,
        max_tokens=3000,
        response_format=ProcessedArticle
    )
    # Return the parsed Pydantic model
    return response.choices[0].message.parsed.model_dump()

def update_article_summary(existing_summary: str, new_article_text: str) -> dict:
    
    max_length = 2000  # adjust this limit as needed
    if len(new_article_text) > max_length:
        truncated_text = f"{new_article_text[:max_length]}..."
    else:
        truncated_text = new_article_text

    system_message = "Si profesionalny novinár, ktorý spracúvava články pre webovú publikáciu."
    user_message = f"""
    Máme existujúce zhrnutie článku a nový text článku, ktorý môže obsahovať nové informácie.
    Skombinuj ich tak, aby bolo zachované všetko dôležité a aby nové informácie boli začlenené správne.
    
    Aktualizuj:
    - "intro": Krátky úvodný pútavý text článku pár slovami.
    - "summary": Sumarizacia článku v neutrálnej reči so spracovaním všetkých informácií, zachovaním formátovania a doplnením nových informacii ak nejake su.
    
    Pôvodné zhrnutie:
    {existing_summary}
    
    Nový článok:
    {truncated_text}
    
    Vráť len platný JSON bez akýchkoľvek komentárov alebo dodatočného textu.
    """

    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.7,
        max_tokens=3000,
        response_format=UpdatedArticle
    )

    return response.choices[0].message.parsed.model_dump()