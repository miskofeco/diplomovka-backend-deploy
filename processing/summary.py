from pydantic import BaseModel, Field
from typing import List, Dict
import openai
from openai import OpenAI
import os
from dotenv import load_dotenv
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import re
import logging

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL")
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

PREDEFINED_CATEGORIES = ["Politika", "Ekonomika", "Šport", "Kultúra", "Technológie", "Zdravie", "Veda", "Komentáre", "Cestovanie", "Blog"]
PREDEFINED_TAGS = ["Trendy", "Aktuálne", "18+", "Krimi", "Zaujímavosti","Auto-moto", "Zivotný-štyl", "Ostatné", "Zo sveta", "Domáce", "Slovensko", "Svet", "Európa", "Amerika", "Ázia", "Afrika", "Austrália", "Pre mladých", "Pre Ženy","Pre Študentov", "Cirkev", "Umelá Inteligencia", "IT", "Podnikanie", "Umenie", "Reality-show"]

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

class Event(BaseModel):
    actor: str = Field(..., description="Kto vykonal akciu")
    action: str = Field(..., description="Čo sa stalo")
    location: str | None = Field(None, description="Kde sa to stalo")
    time: str | None = Field(None, description="Kedy sa to stalo")
    target: str | None = Field(None, description="Na kom/čom bola akcia vykonaná")
    context: str | None = Field(None, description="Dodatočný kontext")

def get_category_and_tags(text: str) -> dict:
    system_message = "Si profesionálny novinár, ktorý kategorizuje články."
    user_message = f"""
    Urč kategóriu a tagy pre nasledujúci text článku. Vráť výsledok v JSON formáte:
    - "category": Vyber JEDNU kategóriu z: {PREDEFINED_CATEGORIES}
    - "tags": Vyber 1-4 najvhodnejšie tagy z: {PREDEFINED_TAGS}

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
        max_tokens=1024,
        response_format=CategoryTags
    )
    logging.debug(f"Response content: {response.choices[0].message.content}")
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
        max_tokens=1024,
        response_format=TitleIntro
    )
    logging.debug(f"Response content: {response.choices[0].message.content}")
    return response.choices[0].message.parsed.model_dump()

def extract_events(text: str) -> List[str]:
    """Extrahuje kľúčové udalosti z textu článku ako zoznam textových popisov"""
    system_message = """Si expertný analytik, ktorý identifikuje kľúčové udalosti v texte.
    Pre každú udalosť vytvor stručný, jasný popis v jednej vete.
    Zameraj sa na:
    - Čo sa stalo
    - Kto bol zapojený
    - Kde a kedy sa to stalo (ak je uvedené)
    
    Vráť zoznam udalostí, každú v samostatnom riadku."""

    user_message = f"""Analyzuj nasledujúci text a identifikuj hlavné udalosti.
    Pre každú udalosť vytvor stručný popis.

    Text článku:
    {text}

    Vráť zoznam udalostí, každú v samostatnom riadku.
    Príklad:
    Prezident Novák navštívil v pondelok Bratislavu
    Parlament schválil nový zákon o daniach
    Minister oznámil svoju rezignáciu
    """

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            max_tokens=2048
        )

        # Rozdelíme odpoveď na riadky a odstránime prázdne riadky
        events = [
            line.strip() 
            for line in response.choices[0].message.content.split('\n') 
            if line.strip()
        ]
        
        return events

    except Exception as e:
        logging.error(f"Error extracting events: {e}")
        return []

def get_summary(text: str) -> dict:
    """Hlavná funkcia pre generovanie súhrnu"""
    try:
        # Najprv extrahujeme udalosti
        events = extract_events(text)
        logging.debug(f"Extracted events: {events}")

        # Vytvoríme text udalostí
        events_text = "\n".join([f"- {event}" for event in events])

        # Generujeme súhrn na základe textu a udalostí
        system_message = "Si profesionálny novinár, ktorý vytvára výstižné a informatívne súhrny."
        
        user_message = f"""Vytvor súhrn na základe nasledujúcich informácií.
        Vráť odpoveď ako JSON s poľom 'summary'.

        Pôvodný text článku:
        {text}

        Identifikované kľúčové udalosti:
        {events_text}

        Vytvor pútavý a informatívny súhrn, ktorý zachytáva podstatu článku
        a logicky prepája identifikované udalosti.

        Formát odpovede:
        {{
            "summary": "text súhrnu"
        }}
        """

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=2048,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        return {"summary": result.get("summary", "")}

    except Exception as e:
        logging.error(f"Error in get_summary: {e}")
        return {"summary": ""}

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
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.3,
        max_tokens=2048,
        response_format={ "type": "json_object" }  # Changed from "json" to "json_object"
    )
    
    logging.debug(f"Response content: {response.choices[0].message.content}")
    # Parse the JSON response manually
    result = json.loads(response.choices[0].message.content)
    return result

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
    """Process article text and return structured data"""
    try:
        # Get category and tags
        cat_tags = get_category_and_tags(text)
        
        # Get title and intro
        title_intro = get_title_and_intro(text)
        
        # Get summary
        summary = get_summary(text)
        
        
        # Combine all results
        article_data = {
            "category": cat_tags.get("category"),
            "tags": cat_tags.get("tags", []),
            "title": title_intro.get("title"),
            "intro": title_intro.get("intro"),
            "summary": summary.get("summary")
        }
        logging.debug(f"Article data before processing: {article_data}")
        return article_data
        
    except Exception as e:
        logging.error(f"Error in process_article: {str(e)}", exc_info=True)
        return {
            "category": "",
            "tags": [],
            "title": "",
            "intro": "",
            "summary": "",
            "political_orientation": {},
            "facts": []
        }

def update_article_summary(existing_summary: str, new_article_text: str) -> dict:
    """Update existing article with new information"""
    if len(new_article_text) > 2000:
        new_article_text = f"{new_article_text[:2000]}..."
    
    # Extract new information from the article
    system_message = "Si profesionálny novinár, ktorý identifikuje nové informácie v článku."
    user_message = f"""
    Porovnaj existujúci súhrn s novým článkom a identifikuj iba nové, doplňujúce informácie.
    Nevracaj celý súhrn, iba nové informácie, ktoré nie sú v existujúcom súhrne.
    Ak nie sú žiadne nové informácie, vráť prázdny reťazec.

    Existujúci súhrn:
    {existing_summary}

    Nový článok:
    {new_article_text}

    Vráť JSON s poľom 'new_information', ktoré obsahuje iba nové informácie.
    """
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            max_tokens=2048,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        new_info = result.get("new_information", "")
        
        # Ensure new_info is a string before calling strip()
        if isinstance(new_info, list):
            new_info = " ".join(new_info)
        
        new_info = new_info.strip()
        
        # If there's new information, update the summary
        if new_info:
            # Get title and intro for the new article
            title_intro = get_title_and_intro(new_article_text)
            
            # Create updated summary by appending new information
            updated_summary = existing_summary
            if not updated_summary.endswith("."):
                updated_summary += "."
                
            updated_summary += f" {new_info}"
            
            return {
                "intro": title_intro["intro"],
                "summary": updated_summary
            }
        else:
            # No new information, keep existing summary
            title_intro = get_title_and_intro(new_article_text)
            return {
                "intro": title_intro["intro"],
                "summary": existing_summary
            }
    except Exception as e:
        logging.error(f"Error updating article summary: {str(e)}")
        # In case of error, keep the existing summary
        title_intro = get_title_and_intro(new_article_text)
        return {
            "intro": title_intro["intro"],
            "summary": existing_summary
        }
