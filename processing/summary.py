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
        max_tokens=500,
        response_format=TitleIntro
    )
    logging.debug(f"Response content: {response.choices[0].message.content}")
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
    logging.debug(f"Response content: {response.choices[0].message.content}")
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
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.3,
        max_tokens=500,
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
        
        # Get political orientation
        orientation = analyze_political_orientation(text)
        
        # Get fact check results
        fact_check_results = fact_check_article(text)
        
        # Combine all results
        article_data = {
            "category": cat_tags.get("category"),
            "tags": cat_tags.get("tags", []),
            "title": title_intro.get("title"),
            "intro": title_intro.get("intro"),
            "summary": summary.get("summary"),
            "political_orientation": orientation,
            "facts": fact_check_results  # fact_check_results is already a list
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
    
    # Only update intro and summary for existing articles
    title_intro = get_title_and_intro(new_article_text)
    summary = get_summary(f"{existing_summary}\n\nNové informácie:\n{new_article_text}")
    
    return {
        "intro": title_intro["intro"],
        "summary": summary["summary"]
    }

def search_web(query: str, num_results: int = 3) -> List[Dict]:
    """
    Vyhľadá informácie na webe pomocou Google Search API
    Returns: List of dicts with {'url': '', 'title': '', 'snippet': ''}
    """
    # Tu by ste použili reálne Google Search API alebo alternatívnu službu
    # Toto je zjednodušená implementácia
    search_url = f"https://www.googleapis.com/customsearch/v1"
    params = {
        'key': os.getenv('GOOGLE_SEARCH_API_KEY'),
        'cx': os.getenv('GOOGLE_SEARCH_CX'),
        'q': quote(query),
        'num': num_results
    }
    
    try:
        response = requests.get(search_url, params=params)
        results = response.json().get('items', [])
        return [{'url': r['link'], 'title': r['title'], 'snippet': r['snippet']} for r in results]
    except Exception as e:
        logging.error(f"Search error: {e}")
        return []

def extract_facts(text: str) -> List[Dict]:
    """Extract facts from text using LLM"""
    system_message = """Si expertný fact-checker. Tvojou úlohou je:
    1. Identifikovať faktické tvrdenia z textu
    2. Transformovať ich do overiteľnej podoby
    3. Vrátiť ich v štruktúrovanom formáte JSON
    
    Dôležité: Dôkladne over, že výsledný JSON je validný - každý string musí byť uzavretý 
    v úvodzovkách a nesmú v ňom byť žiadne neuzavreté reťazce.
    """
    
    user_message = f"""Analyzuj nasledujúci text a identifikuj faktické tvrdenia.
    Pre každé tvrdenie vytvor:
    - Presné znenie tvrdenia
    - Kľúčové slová pre vyhľadávanie
    - Kontext tvrdenia
    
    Text:
    {text[:3000]}  # Limit text length to avoid token overflow
    
    Vráť validný JSON objekt s kľúčom "facts", ktorý obsahuje array, kde každý objekt má:
    - "claim": presné znenie tvrdenia
    - "search_query": optimalizovaný vyhľadávací dotaz
    - "context": relevantný kontext z textu
    """
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            max_tokens=1000,
            response_format={"type": "json_object"}
        )
        
        # Get the response content
        content = response.choices[0].message.content
        logging.debug(f"Response content: {content}")
        
        # Try to parse the JSON
        try:
            result = json.loads(content)
            # Return the "facts" array or an empty list if not present
            return result.get("facts", [])
        except json.JSONDecodeError as e:
            logging.error(f"JSON parsing error: {e}")
            logging.error(f"Raw response: {content}")
            # Return empty list instead of raising an exception
            return []
            
    except Exception as e:
        logging.error(f"Error calling OpenAI API: {e}")
        return []

def verify_fact(claim: str, search_results: List[Dict]) -> Dict:
    """Verifikuje fakt pomocou nájdených zdrojov"""
    system_message = """Si expertný fact-checker. Tvojou úlohou je overiť faktické tvrdenie
    pomocou poskytnutých zdrojov a určiť jeho pravdivosť."""
    
    sources_text = "\n".join([
        f"Zdroj {i+1}:\nURL: {r['url']}\nTitle: {r['title']}\nText: {r['snippet']}"
        for i, r in enumerate(search_results)
    ])
    
    user_message = f"""Over nasledujúce tvrdenie pomocou poskytnutých zdrojov:
    
    Tvrdenie: {claim}
    
    Zdroje:
    {sources_text}
    
    Vráť JSON s:
    - "verification": hodnotenie ["TRUE", "PARTLY_TRUE", "FALSE", "UNVERIFIABLE"]
    - "explanation": zdôvodnenie hodnotenia
    - "sources": zoznam URL zdrojov podporujúcich hodnotenie
    """
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.3,
        max_tokens=500,
        response_format={ "type": "json_object" }
    )
    
    logging.debug(f"Response content: {response.choices[0].message.content}")
    return json.loads(response.choices[0].message.content)

def fact_check_article(text: str) -> list:
    try:
        # Changed from get_facts_from_text to extract_facts
        facts = extract_facts(text)
        
        fact_check_results = []
        for fact in facts:
            if isinstance(fact, str):
                try:
                    fact = json.loads(fact)
                except json.JSONDecodeError:
                    logging.warning(f"Failed to parse fact as JSON: {fact}")
                    continue
                    
            if not isinstance(fact, dict):
                logging.warning(f"Unexpected fact format: {fact}")
                continue
                
            search_query = fact.get('search_query')
            if not search_query:
                logging.warning(f"No search query found in fact: {fact}")
                continue
                
            search_results = search_web(search_query)
            # Process search results...
            fact_check_results.append({
                'fact': fact,
                'search_results': search_results,
                'verification_status': verify_fact(fact, search_results)
            })
            
        return fact_check_results
        
    except Exception as e:
        logging.error(f"Error in fact checking: {str(e)}", exc_info=True)
        return []  # Return empty list in case of error

def generate_fact_check_summary(verified_facts: List[Dict]) -> str:
    """Generuje súhrnné hodnotenie fact-checkingu"""
    system_message = "Si expertný fact-checker. Vytvor súhrnné hodnotenie overených faktov."
    
    facts_summary = "\n".join([
        f"Tvrdenie: {f['claim']}\nHodnotenie: {f['verification']}\nVysvetlenie: {f['explanation']}"
        for f in verified_facts
    ])
    
    user_message = f"""Vytvor súhrnné hodnotenie nasledujúcich overených faktov:
    
    {facts_summary}
    
    Vráť JSON s:
    - "summary": celkové zhodnotenie článku z pohľadu faktickej presnosti
    - "trust_score": číselné hodnotenie dôveryhodnosti (0-100)
    """
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.3,
        max_tokens=500,
        response_format={ "type": "json_object" }
    )
    
    logging.debug(f"Response content: {response.choices[0].message.content}")
    return json.loads(response.choices[0].message.content)

def create_annotated_summary(summary: str, verified_facts: List[Dict]) -> Dict:
    """Vytvorí anotovanú verziu súhrnu s odkazmi na zdroje"""
    annotated_text = summary
    annotations = []
    
    for fact in verified_facts:
        # Nájdi výskyt tvrdenia v súhrne
        if fact['claim'] in summary:
            # Vytvor anotáciu s odkazmi na zdroje
            annotation = {
                'text': fact['claim'],
                'verification': fact['verification'],
                'sources': fact['sources']
            }
            annotations.append(annotation)
    
    return {
        'text': annotated_text,
        'annotations': annotations
    }

def process_article_data(article_data: dict) -> dict:
    """Convert dict fields to JSON strings before database insertion"""
    processed_data = article_data.copy()
    
    # Handle political_orientation specially - extract just the orientation value
    if isinstance(processed_data.get('political_orientation'), dict):
        orientation_value = processed_data['political_orientation'].get('orientation', 'neutral')
        # Store political orientation as JSON string for JSONB column
        processed_data['political_orientation'] = json.dumps(orientation_value)
    
    # Convert other dictionary fields to JSON strings
    for key, value in processed_data.items():
        if key != 'political_orientation' and isinstance(value, dict):
            processed_data[key] = json.dumps(value)
        # Handle nested dictionaries in lists
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    value[i] = json.dumps(item)
    
    logging.debug(f"Processed article data: {processed_data}")
    return processed_data
