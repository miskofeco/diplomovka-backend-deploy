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
PREDEFINED_TAGS = ["Trendy", "Aktualne", "18+", "Krimi", "Zaujimavosti", "Zivotne-styl", "Ostatne"]

# Pydantic model
class ProcessedArticle(BaseModel):
    title: str = Field(..., title="title", description="Nazov clanku")
    intro: str = Field(..., title="intro", description="Uvodny putavy text clanku par slovami")
    summary: str = Field(..., title="summary", description="prepis clanku v neutralnej reci so spracovanim vsetkych informacii")
    category: str
    tags: List[str] 


system_message = "Si nápomocný asistent..."
user_message = f"""
    Spracuj nasledujúci text článku a vráť výsledok
    Na zaklade clanku urči kategoriu z nasledujúcich možností: {PREDEFINED_CATEGORIES}
    Na zaklade clanku urči tagy z nasledujúcich možností: {PREDEFINED_TAGS}
    Text článku:
    video Temné mračná nad tradičnou futbalovou baštou a čo prinesie Martin Škrtel do Trnavy\n\nNajvyššia slovenská futbalová liga sa prehupla do nadstavbovej časti, ktorá má za sebou úvodné kolo. Po ňom sa diali veci vo vrchnej i v spodnej šestke. Takisto uvidíme, čo prinesie do Spartaka Trnava ich nový športový riaditeľ Martin Škrtel. Viac sa už dozviete v 29. epizóde relácie Kam si to kopol?
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
output = response.choices[0].message.parsed
print(output)




