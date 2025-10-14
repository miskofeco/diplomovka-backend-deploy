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
PREDEFINED_TAGS = ["Trendy", "Aktuálne", "18+", "Krimi", "Zaujímavosti","Auto-moto", "História", "Životný-štyl", "Ostatné", "Zo sveta", "Slovensko", "Svet", "Európa", "Amerika", "Ázia", "Afrika", "Austrália", "Pre mladých", "Pre Ženy","Pre Študentov", "Cirkev", "Umelá Inteligencia", "IT", "Podnikanie", "Umenie", "Reality-show"]

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

# Add verification models
class CategoryTagsVerification(BaseModel):
    is_accurate: bool = Field(..., description="Whether the categorization is accurate")
    feedback: str = Field(..., description="Detailed feedback on the categorization")
    
class TitleIntroVerification(BaseModel):
    is_accurate: bool = Field(..., description="Whether the title and intro are accurate")
    feedback: str = Field(..., description="Detailed feedback on the title and intro")
    
class SummaryVerification(BaseModel):
    is_accurate: bool = Field(..., description="Whether the summary is accurate and not hallucinated")
    feedback: str = Field(..., description="Detailed feedback on the summary")

def get_category_and_tags(text: str, feedback: str = None) -> dict:
    """Generate category and tags with optional feedback from previous attempts"""
    system_message = "Si profesionálny novinár, ktorý kategorizuje články."
    
    user_message = f"""
    Urč kategóriu a tagy pre nasledijúci text článku. Vráť výsledok v JSON formáte:
    - "category": Vyber JEDNU kategóriu z: {PREDEFINED_CATEGORIES}
    - "tags": Vyber 1-4 najvhodnejšie tagy z: {PREDEFINED_TAGS}

    Text článku:
    {text}
    """
    
    # Add feedback from verification if provided
    if feedback:
        user_message += f"""
        
        DÔLEŽITÉ: Predcházajúci pokus bol zamietnutý z nasledujúceho dôvodu:
        {feedback}
        
        Prosím, zohľadni túto spätnú väzbu a vyhni sa rovnakým chybám.
        """
    
    user_message += "\nVráť len platný JSON bez komentárov."
    
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

def get_title_and_intro(text: str, feedback: str = None) -> dict:
    """Generate title and intro with optional feedback from previous attempts"""
    system_message = "Si profesionálny novinár, ktorý píše pútavé titulky a úvody."
    
    user_message = f"""
    Vytvor pútavý názov a krátky úvod pre nasledujúci text článku. Vráť v JSON formáte:
    - "title": Pútavý názov článku
    - "intro": Krátky úvod, pútavý text pár slovami

    Text článku:
    {text}
    """
    
    # Add feedback from verification if provided
    if feedback:
        user_message += f"""
        
        DÔLEŽITÉ: Predcházajúci pokus bol zamietnutý z nasledijúceho dôvodu:
        {feedback}
        
        Prosím, zohľadni túto spätnú väzbu a vyhni sa rovnakým chybám.
        Zameraj sa na presnosť, relevantnosť a vyhni sa halucinovaným informáciám.
        """
    
    user_message += "\nVráť len platný JSON bez komentárov."
    
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

def get_summary(text: str, feedback: str = None) -> dict:
    """Generate summary with optional feedback from previous attempts"""
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
        """
        
        # Add feedback from verification if provided
        if feedback:
            user_message += f"""
            
            DÔLEŽITÉ: Predcházajúci pokus bol zamietnutý z nasledijúceho dôvodu:
            {feedback}
            
            Prosím, zohľadni túto spätnú väzbu a vyhni sa rovnakým chybám.
            Zameraj sa na:
            - Presnosť voči pôvodnému textu
            - Objektívnosť a neutralitu
            - Vyhni sa halucinovaným informáciám
            - Logické usporiadanie informácií
            """

        user_message += """
        
        Vytvor pútavý a informatívny súhrn, ktorý zachytáva podstatu článku
        a logicky prepája identifikované udalosti.

        Formát odpovede:
        {
            "summary": "text súhrnu"
        }
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

def verify_category_tags(original_text: str, generated_data: dict, max_retries: int = 3) -> dict:
    """Verify category and tags accuracy with retry mechanism"""
    
    def _verify_once(text: str, data: dict) -> dict:
        system_message = """Si expertný verifikátor obsahu. Tvojou úlohou je overiť presnosť kategorizácie článku.
        Skontroluj:
        1. Či kategória presne zodpovedá obsahu článku
        2. Či tagy sú relevantné a nie sú vymyslené
        3. Či nie sú prítomné halucinované informácie
        
        DÔLEŽITÉ: Buď veľmi špecifický vo svojom hodnotení a uveď presné dôvody prečo je kategorizácia správna alebo nesprávna.
        """
        
        user_message = f"""
        Skontroluj presnosť nasledujúcej kategorizácie voči pôvodnému textu článku.
        
        Pôvodný text článku:
        {text}
        
        Vygenerovaná kategorizácia:
        Kategória: {data.get('category')}
        Tagy: {data.get('tags')}
        
        Dostupné kategórie: {PREDEFINED_CATEGORIES}
        Dostupné tagy: {PREDEFINED_TAGS}
        
        Vráť JSON s:
        - "is_accurate": true/false
        - "feedback": detailné zdôvodnenie hodnotenia s konkrétnymi problémami ak existujú:
          * Prečo je kategória správna/nesprávna
          * Ktoré tagy sú relevantné/irelevantné a prečo
          * Aké konkrétne halucinované informácie boli identifikované
          * Aké alternatívy by boli lepšie
        """
        
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            max_tokens=2048,
            response_format=CategoryTagsVerification
        )
        
        return response.choices[0].message.parsed.model_dump()
    
    # Verification loop with retries
    current_data = generated_data.copy()
    previous_feedback = None
    
    for attempt in range(max_retries):
        logging.info(f"Verifying category/tags - attempt {attempt + 1}/{max_retries}")
        
        verification = _verify_once(original_text, current_data)
        
        if verification["is_accurate"]:
            logging.info("Category/tags verification passed")
            return current_data
        
        previous_feedback = verification["feedback"]
        logging.warning(f"Category/tags verification failed: {previous_feedback}")
        
        if attempt < max_retries - 1:  # Don't regenerate on last attempt
            logging.info("Regenerating category/tags with feedback...")
            current_data = get_category_and_tags(original_text, previous_feedback)
    
    logging.error("Category/tags verification failed after all retries")
    return current_data  # Return last attempt even if not verified

def verify_title_intro(original_text: str, generated_data: dict, max_retries: int = 3) -> dict:
    """Verify title and intro accuracy with retry mechanism"""
    
    def _verify_once(text: str, data: dict) -> dict:
        system_message = """Si expertný verifikátor obsahu. Tvojou úlohou je overiť presnosť titulku a úvodu článku.
        Skontroluj:
        1. Či titulok presne zodpovedá obsahu článku
        2. Či úvod je relevantný a pútavý
        3. Či nie sú prítomné halucinované informácie
        4. Či titulok nie je zavádzajúci
        
        DÔLEŽITÉ: Buď veľmi špecifický vo svojom hodnotení a uveď presné dôvody prečo je obsah správny alebo nesprávny.
        """
        
        user_message = f"""
        Skontroluj presnosť nasledujúceho titulku a úvodu voči pôvodnému textu článku.
        
        Pôvodný text článku:
        {text}
        
        Vygenerovaný obsah:
        Titulok: {data.get('title')}
        Úvod: {data.get('intro')}
        
        Vráť JSON s:
        - "is_accurate": true/false
        - "feedback": detailné zdôvodnenie hodnotenia s konkrétnymi problémami ak existujú:
          * Prečo je titulok správny/nesprávny/zavádzajúci
          * Či úvod správne reflektuje obsah článku
          * Aké konkrétne halucinované informácie boli identifikované
          * Aké zmeny by boli potrebné
          * Konkrétne návrhy na zlepšenie
        """
        
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            max_tokens=1024,
            response_format=TitleIntroVerification
        )
        
        return response.choices[0].message.parsed.model_dump()
    
    # Verification loop with retries
    current_data = generated_data.copy()
    previous_feedback = None
    
    for attempt in range(max_retries):
        logging.info(f"Verifying title/intro - attempt {attempt + 1}/{max_retries}")
        
        verification = _verify_once(original_text, current_data)
        
        if verification["is_accurate"]:
            logging.info("Title/intro verification passed")
            return current_data
        
        previous_feedback = verification["feedback"]
        logging.warning(f"Title/intro verification failed: {previous_feedback}")
        
        if attempt < max_retries - 1:  # Don't regenerate on last attempt
            logging.info("Regenerating title/intro with feedback...")
            current_data = get_title_and_intro(original_text, previous_feedback)
    
    logging.error("Title/intro verification failed after all retries")
    return current_data  # Return last attempt even if not verified

def verify_summary(original_text: str, generated_data: dict, max_retries: int = 3) -> dict:
    """Verify summary accuracy with retry mechanism"""
    
    def _verify_once(text: str, data: dict) -> dict:
        system_message = """Si expertný verifikátor obsahu. Tvojou úlohou je overiť presnosť súhrnu článku.
        Skontroluj:
        1. Či súhrn presne zachytáva hlavné body článku
        2. Či nie sú prítomné halucinované informácie
        3. Či súhrn je objektívny a neutrálny
        4. Či súhrn neobsahuje informácie, ktoré nie sú v pôvodnom texte
        5. Či súhrn je logicky usporiadaný
        
        DÔLEŽITÉ: Buď veľmi špecifický vo svojom hodnotení a uveď presné dôvody prečo je súhrn správny alebo nesprávny.
        """
        
        user_message = f"""
        Skontroluj presnosť nasledujúceho súhrnu voči pôvodnému textu článku.
        
        Pôvodný text článku:
        {text}
        
        Vygenerovaný súhrn:
        {data.get('summary')}
        
        Vráť JSON s:
        - "is_accurate": true/false
        - "feedback": detailné zdôvodnenie hodnotenia s konkrétnymi problémami ak existujú:
          * Ktoré hlavné body článku chýbajú v súhrne
          * Aké konkrétne halucinované informácie boli identifikované (cituj presné časti)
          * Či je súhrn objektívny alebo obsahuje subjektívne hodnotenia
          * Aké informácie sú v súhrne, ale nie sú v pôvodnom texte
          * Problémy s logickým usporiadaním
          * Konkrétne návrhy na zlepšenie súhrnu
        """
        
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            max_tokens=3000,
            response_format=SummaryVerification
        )
        
        return response.choices[0].message.parsed.model_dump()
    
    # Verification loop with retries
    current_data = generated_data.copy()
    previous_feedback = None
    
    for attempt in range(max_retries):
        logging.info(f"Verifying summary - attempt {attempt + 1}/{max_retries}")
        
        verification = _verify_once(original_text, current_data)
        
        if verification["is_accurate"]:
            logging.info("Summary verification passed")
            return current_data
        
        previous_feedback = verification["feedback"]
        logging.warning(f"Summary verification failed: {previous_feedback}")
        
        if attempt < max_retries - 1:  # Don't regenerate on last attempt
            logging.info("Regenerating summary with feedback...")
            current_data = get_summary(original_text, previous_feedback)
    
    logging.error("Summary verification failed after all retries")
    return current_data  # Return last attempt even if not verified

def process_article(text: str) -> dict:
    """Process article text and return structured data with verification"""
    try:
        logging.info("Starting article processing with verification")
        
        # Step 1: Generate category and tags with verification
        logging.info("Generating and verifying category/tags...")
        cat_tags = get_category_and_tags(text)
        verified_cat_tags = verify_category_tags(text, cat_tags)
        
        # Step 2: Generate title and intro with verification
        logging.info("Generating and verifying title/intro...")
        title_intro = get_title_and_intro(text)
        verified_title_intro = verify_title_intro(text, title_intro)
        
        # Step 3: Generate summary with verification
        logging.info("Generating and verifying summary...")
        summary = get_summary(text)
        verified_summary = verify_summary(text, summary)
        
        # Combine all verified results
        article_data = {
            "category": verified_cat_tags.get("category"),
            "tags": verified_cat_tags.get("tags", []),
            "title": verified_title_intro.get("title"),
            "intro": verified_title_intro.get("intro"),
            "summary": verified_summary.get("summary")
        }
        
        logging.info("Article processing with verification completed successfully")
        logging.debug(f"Final verified article data: {article_data}")
        return article_data
        
    except Exception as e:
        logging.error(f"Error in process_article with verification: {str(e)}", exc_info=True)
        return {
            "category": "",
            "tags": [],
            "title": "",
            "intro": "",
            "summary": "",
            "political_orientation": {},
            "facts": []
        }

def update_article_summary(existing_summary: str, new_article_text: str, feedback: str = None) -> dict:
    """Update existing article with new information and optional feedback"""
    if len(new_article_text) > 2000:
        new_article_text = f"{new_article_text[:2000]}..."
    
    # Extract new information from the article
    system_message = "Si profesionálny novinár, ktorý identifikuje nové informácie v článku."
    user_message = f"""
    Porovnaj existujúci súhrn s novým článkom a vytvor aktualizovaný súhrn.
    
    INŠTRUKCIE:
    1. Zachovaj všetky dôležité informácie z existujúceho súhrnu
    2. Pridaj nové relevantné informácie z nového článku
    3. Zabezpeč logické prepojenie starých a nových informácií
    4. Odstráň duplicitné informácie
    5. Zachovaj chronologické usporiadanie ak je relevantné

    Existujúci súhrn:
    {existing_summary}

    Nový článok:
    {new_article_text}
    """
    
    # Add feedback if provided
    if feedback:
        user_message += f"""
        
        DÔLEŽITÉ: Predcházajúci pokus bol zamietnutý z nasledijúceho dôvodu:
        {feedback}
        
        Prosím, zohľadni túto spätnú väzbu a vyhni sa rovnakým chybám.
        Zameraj sa na:
        - Zachovanie všetkých pôvodných informácií
        - Presné pridanie iba nových informácií
        - Logické prepojenie obsahu
        - Vyhni sa halucinovaným informáciám
        """

    user_message += """
    
    Vráť JSON s:
    - "summary": aktualizovaný súhrn (kombinujúci starý a nový obsah)
    - "intro": nový úvod pre aktualizovaný článok
    """
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            max_tokens=3000,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        updated_summary = result.get("summary", existing_summary).strip()
        updated_intro = result.get("intro", "").strip()
        
        # Fallback if intro is missing
        if not updated_intro:
            title_intro = get_title_and_intro(f"{existing_summary}\n\n{new_article_text}", feedback)
            updated_intro = title_intro.get("intro", "")
        
        return {
            "intro": updated_intro,
            "summary": updated_summary
        }
        
    except Exception as e:
        logging.error(f"Error updating article summary: {str(e)}")
        # In case of error, try to get at least new intro
        try:
            title_intro = get_title_and_intro(new_article_text, feedback)
            return {
                "intro": title_intro.get("intro", ""),
                "summary": existing_summary  # Keep original summary if update fails
            }
        except:
            return {
                "intro": "",
                "summary": existing_summary
            }

def verify_article_update(original_summary: str, new_article_text: str, updated_data: dict, max_retries: int = 3) -> dict:
    """Verify updated article summary accuracy with retry mechanism"""
    
    def _verify_once(orig_summary: str, new_text: str, data: dict) -> dict:
        system_message = """Si expertný verifikátor obsahu. Tvojou úlohou je overiť presnosť aktualizácie súhrnu článku.
        Skontroluj:
        1. Či nový súhrn správne integruje nové informácie
        2. Či nedošlo k strate dôležitých informácií z pôvodného súhrnu
        3. Či nie sú prítomné halucinované informácie
        4. Či aktualizácia je logická a koherentná
        5. Či úvod správne reflektuje aktualizovaný obsah
        
        DÔLEŽITÉ: Buď veľmi špecifický vo svojom hodnotení a uveď presné dôvody prečo je aktualizácia správna alebo nesprávna.
        """
        
        user_message = f"""
        Skontroluj presnosť nasledujúcej aktualizácie súhrnu článku.
        
        Pôvodný súhrn:
        {orig_summary}
        
        Nový článok (zdroj nových informácií):
        {new_text}
        
        Aktualizovaný obsah:
        Úvod: {data.get('intro')}
        Súhrn: {data.get('summary')}
        
        Vráť JSON s:
        - "is_accurate": true/false
        - "feedback": detailné zdôvodnenie hodnotenia s konkrétnymi problémami ak existujú:
          * Či nový súhrn správne zachováva pôvodné informácie
          * Aké nové informácie boli správne/nesprávne pridané
          * Aké konkrétne halucinované informácie boli identifikované
          * Problémy s logickým prepojením starých a nových informácií
          * Či úvod správne reflektuje aktualizovaný obsah
          * Konkrétne návrhy na zlepšenie aktualizácie
        """
        
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            max_tokens=2048,
            response_format=SummaryVerification  # Reuse existing verification model
        )
        
        return response.choices[0].message.parsed.model_dump()
    
    # Verification loop with retries
    current_data = updated_data.copy()
    previous_feedback = None
    
    for attempt in range(max_retries):
        logging.info(f"Verifying article update - attempt {attempt + 1}/{max_retries}")
        
        verification = _verify_once(original_summary, new_article_text, current_data)
        
        if verification["is_accurate"]:
            logging.info("Article update verification passed")
            return current_data
        
        previous_feedback = verification["feedback"]
        logging.warning(f"Article update verification failed: {previous_feedback}")
        
        if attempt < max_retries - 1:  # Don't regenerate on last attempt
            logging.info("Regenerating article update with feedback...")
            current_data = update_article_summary(original_summary, new_article_text, previous_feedback)
    
    logging.error("Article update verification failed after all retries")
    return current_data  # Return last attempt even if not verified
