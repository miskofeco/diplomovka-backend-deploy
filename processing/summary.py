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

# Add new constants
POLITICAL_SOURCES = {
    "pravda.sk": "left",
    "aktuality.sk": "neutral",
    "dennikn.sk": "center-left",
    "sme.sk": "center-right",
    "postoj.sk": "right",
    # Add more sources as needed
}

class CategoryTags(BaseModel):
    category: str
    tags: List[str]

class TitleIntro(BaseModel):
    title: str = Field(..., title="title", description="Názov článku")
    intro: str = Field(..., title="intro", description="Úvodný pútavý text článku pár slovami")

class ArticleSummary(BaseModel):
    summary: str = Field(..., title="summary", description="Sumarizácia článku v neutrálnej reči")

class PoliticalOrientation(BaseModel):
    orientation: str = Field(..., description="Political orientation of the article")
    confidence: float = Field(..., description="Confidence score of the assessment")
    reasoning: str = Field(..., description="Reasoning behind the assessment")

def get_category_and_tags(text: str) -> dict:
    system_message = "Si profesionálny novinár, ktorý kategorizuje články."
    user_message = f"""
    Urč kategóriu a tagy pre nasledujúci text článku. Vráť výsledok v JSON formáte:
    - "category": Vyber JEDNU kategóriu z: {PREDEFINED_CATEGORIES}
    - "tags": Vyber 1-3 najvhodnejšie tagy z: {PREDEFINED_TAGS}

    Text článku:
    {text}

    Vráť len platný JSON bez komentárov.
    """
    
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.3,
        max_tokens=500,
        response_format=CategoryTags
    )
    return response.choices[0].message.parsed.model_dump()

def get_title_and_intro(text: str) -> dict:
    system_message = "Si profesionálny novinár, ktorý píše pútavé titulky a úvody."
    user_message = f"""
    Vytvor pútavý názov a krátky úvod pre nasledujúci text článku. Vráť v JSON formáte:
    - "title": Pútavý názov článku
    - "intro": Krátky úvod, pútavý text pár slovami

    Text článku:
    {text}

    Vráť len platný JSON bez komentárov.
    """
    
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.7,
        max_tokens=500,
        response_format=TitleIntro
    )
    return response.choices[0].message.parsed.model_dump()

def get_summary(text: str) -> dict:
    system_message = "Si profesionálny novinár, ktorý píše výstižné zhrnutia."
    user_message = f"""
    Vytvor sumarizáciu nasledujúceho textu článku. Vráť v JSON formáte:
    - "summary": Sumarizácia článku do pútavého textu so spracovaním všetkých informácií. 
    Zahrň formátovanie – odsadenie, odseky a vhodné riadkové zlomy.

    Text článku:
    {text}

    Vráť len platný JSON bez komentárov.
    """
    
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.7,
        max_tokens=2000,
        response_format=ArticleSummary
    )
    return response.choices[0].message.parsed.model_dump()

def analyze_political_orientation(text: str) -> dict:
    """Analyze political orientation of the article text"""
    system_message = """Si expertný politický analytik. Tvojou úlohou je analyzovať politickú orientáciu článku.
    Hodnotenie musí byť založené na objektívnych kritériách:
    
    1. Použitý jazyk a tón
    2. Výber citovaných zdrojov
    3. Spôsob prezentovania faktov
    4. Prítomnosť ideologických markerov
    
    Orientácia musí byť jedna z:
    - "left" (ľavicová)
    - "center-left" (stredo-ľavá)
    - "neutral" (neutrálna)
    - "center-right" (stredo-pravá)
    - "right" (pravicová)
    
    Vráť percentuálne rozloženie orientácie, kde súčet musí byť 100%."""

    user_message = f"""Analyzuj politickú orientáciu nasledujúceho textu. 
    Vráť JSON s:
    - "orientation": dominantná orientácia ["left", "center-left", "neutral", "center-right", "right"]
    - "confidence": číslo od 0.0 do 1.0 vyjadrujúce istotu hodnotenia
    - "reasoning": stručné zdôvodnenie hodnotenia
    - "distribution": percentuálne rozloženie orientácií (súčet 100%)
    
    Text článku:
    {text}
    """
    
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.3,
        max_tokens=500,
        response_format={
            "orientation": str,
            "confidence": float,
            "reasoning": str,
            "distribution": {
                "left_percent": float,
                "center_left_percent": float,
                "neutral_percent": float,
                "center_right_percent": float,
                "right_percent": float
            }
        }
    )
    return response.choices[0].message.parsed

def calculate_source_orientation(urls: List[str]) -> dict:
    """Calculate orientation statistics based on article sources"""
    counts = {"left": 0, "center-left": 0, "neutral": 0, "center-right": 0, "right": 0}
    total = 0
    
    for url in urls:
        domain = url.split("//")[-1].split("/")[0]
        if orientation := POLITICAL_SOURCES.get(domain):
            counts[orientation] += 1
            total += 1
    
    if total == 0:
        return {
            "left_percent": 0,
            "center_left_percent": 0,
            "neutral_percent": 100,
            "center_right_percent": 0,
            "right_percent": 0
        }
    
    return {
        "left_percent": (counts["left"] / total) * 100,
        "center_left_percent": (counts["center-left"] / total) * 100,
        "neutral_percent": (counts["neutral"] / total) * 100,
        "center_right_percent": (counts["center-right"] / total) * 100,
        "right_percent": (counts["right"] / total) * 100
    }

def process_article(text: str) -> dict:
    """Process article text with separate API calls for each part"""
    if len(text) > 2000:
        text = f"{text[:2000]}..."
    
    # Get each part separately
    cat_tags = get_category_and_tags(text)
    title_intro = get_title_and_intro(text)
    summary = get_summary(text)
    political = analyze_political_orientation(text)
    
    # Combine results
    return {
        "category": cat_tags["category"],
        "tags": cat_tags["tags"],
        "title": title_intro["title"],
        "intro": title_intro["intro"],
        "summary": summary["summary"],
        "political_orientation": political["orientation"],
        "political_confidence": political["confidence"],
        "political_reasoning": political["reasoning"]
    }

def update_article_summary(existing_summary: str, new_article_text: str) -> dict:
    """Update existing article with new information"""
    if len(new_article_text) > 2000:
        new_article_text = f"{new_article_text[:2000]}..."
    
    # Only update intro and summary for existing articles
    title_intro = get_title_and_intro(new_article_text)
    summary = get_summary(f"{existing_summary}\n\nNové informácie:\n{new_article_text}")
    
    return {
        "intro": title_intro["intro"],
        "summary": summary["summary"]
    }
