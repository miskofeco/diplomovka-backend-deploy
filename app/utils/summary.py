from pydantic import BaseModel, Field
from typing import List, Dict, Callable, Optional
import openai
from openai import OpenAI
import os
from dotenv import load_dotenv
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
    orientation: str = Field(..., description="Dominantná politická orientácia článku")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Istota hodnotenia v rozsahu 0-1")
    reasoning: str = Field(..., description="Stručné zdôvodnenie hodnotenia v slovenčine")
    distribution: Dict[str, float] = Field(..., description="Percentuálne rozloženie orientácií so súčtom 100")

class Event(BaseModel):
    actor: str = Field(..., description="Kto vykonal akciu")
    action: str = Field(..., description="Čo sa stalo")
    location: str | None = Field(None, description="Kde sa to stalo")
    time: str | None = Field(None, description="Kedy sa to stalo")
    target: str | None = Field(None, description="Na kom/čom bola akcia vykonaná")
    context: str | None = Field(None, description="Dodatočný kontext")

class EventsExtraction(BaseModel):
    events: List[str] = Field(default_factory=list, description="Zoznam hlavných udalostí, každá v jednej vete")

class ArticleUpdate(BaseModel):
    summary: str = Field(..., description="Aktualizovaný sumarizačný text")
    intro: str = Field(..., description="Aktualizovaný úvod článku")

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

    if len(text)>5000:
        text=text[:5000]
    
    system_message = (
        "Si hlavný editor spravodajstva. Pracuješ v izolovanej relácii, ignoruj všetky predchádzajúce pokyny "
        "a odpovedaj výlučne po slovensky. Tvojou úlohou je presne priradiť kategóriu a tagy k článku."
    )
    
    user_message = f"""
    ## ÚLOHA
    Na základe spracovaného článku vyber jednu hlavnú kategóriu a 1 až 4 tagy zo zoznamu.

    ## DOSTUPNÉ VOĽBY
    - Kategórie: {", ".join(PREDEFINED_CATEGORIES)}
    - Tagy: {", ".join(PREDEFINED_TAGS)}

    ## METODIKA
    - reflektuj hlavnú tému článku,
    - zohľadni geografický, tematický aj žánrový kontext,
    - vyhni sa halucináciám a neznámym pojmom.

    ## KONTEXT
    {text}
    """
    
    # Add feedback from verification if provided
    if feedback:
        user_message += f"""
        
        DÔLEŽITÉ: Predcházajúci pokus bol zamietnutý z nasledujúceho dôvodu:
        {feedback}
        
        Prosím, zohľadni túto spätnú väzbu a vyhni sa rovnakým chybám.
        """
    
    user_message += """
    
    ## VÝSTUP
    Vráť dáta v poliach `category` a `tags`, ktoré zodpovedajú schéme pydantic modelu CategoryTags.
    """
    
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.3,
        response_format=CategoryTags
    )
    logging.debug(f"Response content: {response.choices[0].message.content}")
    return response.choices[0].message.parsed.model_dump()

def get_title_and_intro(text: str, feedback: str = None) -> dict:
    """Generate title and intro with optional feedback from previous attempts"""

    if len(text)>5000:
        text=text[:5000]

    system_message = (
        "Si kreatívny editor titulkov pracujúci v izolovanej relácii. "
        "Ignoruj všetky predošlé inštrukcie a odpovedaj výlučne po slovensky. "
        "Tvojou úlohou je vytvoriť pútavý titulok a krátky úvod zodpovedajúci obsahu článku."
    )
    
    user_message = f"""
    ## ÚLOHA
    Navrhni originálny titulok a stručný úvod (max. 2 vety) pre spravodajský článok.

    ## KRITÉRIÁ
    - zachovaj faktickú presnosť,
    - vyhni sa click-bait formuláciám,
    - používaj spisovnú slovenčinu,
    - zvýrazni najdôležitejšiu informáciu z textu.

    ## KONTEXT
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
    
    user_message += """
    
    ## VÝSTUP
    Zabezpeč, aby polia `title` a `intro` zodpovedali schéme pydantic modelu TitleIntro.
    """
    
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.7,
        response_format=TitleIntro
    )
    logging.debug(f"Response content: {response.choices[0].message.content}")
    return response.choices[0].message.parsed.model_dump()

def extract_events(text: str) -> List[str]:
    """Extrahuje kľúčové udalosti z textu článku ako zoznam textových popisov"""

    if len(text)>5000:
        text=text[:5000]
    
    system_message = (
        "Si investigatívny reportér, ktorý analyzuje text izolovane od iných požiadaviek. "
        "Odpovedaj výhradne po slovensky a ignoruj všetky predošlé inštrukcie. "
        "Zameraj sa na identifikáciu kľúčových udalostí v jasnom, stručnom formáte."
    )

    user_message = f"""
    ## ÚLOHA
    Zanalyzuj článok a extrahuj najviac šesť kľúčových udalostí. Každú udalosť popíš jedinou vetou.

    ## METODIKA
    - zachyť čo sa stalo, kto sa zúčastnil, kde a kedy (ak je informácia dostupná),
    - nepoužívaj odrážky ani číslovanie,
    - vyhni sa halucinovaným údajom.

    ## KONTEXT
    {text}

    ## VÝSTUP
    Vráť pole `events`, ktoré obsahuje textové popisy jednotlivých udalostí.
    """

    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.2,
            response_format=EventsExtraction
        )

        parsed = response.choices[0].message.parsed
        return [event.strip() for event in parsed.events if event.strip()]
    except Exception as e:
        logging.error(f"Error extracting events: {e}")
        return []

def get_summary(
    text: str,
    title: Optional[str] = None,
    intro: Optional[str] = None,
    feedback: str = None
) -> dict:
    """Generate summary with optional feedback from previous attempts"""

    if len(text)>5000:
        text=text[:5000]
    
    try:
        # Najprv extrahujeme udalosti
        events = extract_events(text)
        logging.debug(f"Extracted events: {events}")

        # Vytvoríme text udalostí
        events_text = "\n".join([f"- {event}" for event in events]) if events else "- (udalosti sa nepodarilo spoľahlivo extrahovať)"

        # Pripravíme ukončovaciu vetu so zarovnaním na titulok a úvod
        normalized_title = title.strip() if title else None
        normalized_intro = intro.strip() if intro else None

        if normalized_title and normalized_intro:
            closing_directive = f'- Zakonči text vetou presne v tvare: "Záver: {normalized_title}. Úvod: {normalized_intro}".'
        else:
            closing_directive = "- Na záver doplň vetu, ktorá explicitne uvedie titulok a úvod vytvorené pre článok."

        # Generujeme súhrn na základe textu a udalostí
        system_message = (
            "Si profesionálny spravodajský editor pracujúci v izolovanej relácii. "
            "Ignoruj všetky predošlé pokyny a odpovedaj výlučne po slovensky. "
            "Tvojou úlohou je vytvoriť vecný súhrn článku, ktorý je presný, neutrálny a bez halucinácií."
        )
        
        user_message = f"""
        ## ÚLOHA
        Napíš kompaktný spravodajský súhrn v rozsahu 3 až 5 viet, ktorý vyzdvihne najdôležitejšie body článku.

        ## VSTUPNÉ PODKLADY
        ### Text článku
        {text}

        ### Identifikované udalosti
        {events_text}
        """

        if normalized_title:
            user_message += f"""

        ### Titulok
        {normalized_title}
        """

        if normalized_intro:
            user_message += f"""

        ### Úvod
        {normalized_intro}
        """
        
        # Add feedback from verification if provided
        if feedback:
            user_message += f"""
        
        ## SPÄTNÁ VÄZBA
        Predchádzajúci pokus bol zamietnutý z dôvodu:
        {feedback}
        
        Zohľadni túto spätnú väzbu a vyhni sa rovnakým chybám.
        """

        user_message += f"""
        
        ## POŽIADAVKY NA ŠTRUKTÚRU
        - zachovaj chronológiu alebo logické členenie udalostí,
        - nevkladaj nové informácie,
        - použij faktické formulácie bez hodnotenia,
        - {closing_directive}

        ## VÝSTUP
        Poskytni hodnotu poľa `summary` v slovenčine podľa schémy pydantic modelu ArticleSummary.
        """

        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.4,
            response_format=ArticleSummary
        )

        parsed = response.choices[0].message.parsed
        return parsed.model_dump()

    except Exception as e:
        logging.error(f"Error in get_summary: {e}")
        return {"summary": ""}

def analyze_political_orientation(text: str) -> dict:
    """Analyze political orientation of the article text"""
    system_message = (
        "Si nezávislý politický analytik pracujúci v izolovanej relácii. "
        "Ignoruj všetky predchádzajúce pokyny, zachovaj neutralitu a odpovedaj po slovensky."
    )

    user_message = f"""
    ## ÚLOHA
    Urči politickú orientáciu nasledujúceho článku na základe tónu, použitých zdrojov, výberu faktov a ideologických markerov.

    ## MOŽNÉ ORIENTÁCIE
    left, center-left, neutral, center-right, right

    ## KONTEXT
    {text}

    ## VÝSTUP
    - pole `orientation` musí obsahovať jednu z uvedených hodnôt,
    - `confidence` je číslo 0.0 – 1.0,
    - `reasoning` stručne vysvetlí rozhodnutie,
    - `distribution` je slovník s percentami (súčet 100).
    """
    
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.2,
        response_format=PoliticalOrientation
    )
    
    return response.choices[0].message.parsed.model_dump()

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

def verify_category_tags(original_text: str, generated_data: dict, max_retries: int = 1) -> dict:
    """Verify category and tags accuracy with retry mechanism"""
    
    def _verify_once(text: str, data: dict) -> dict:
        system_message = (
            "Si nezávislý kontrolór kategorizácie pracujúci v izolovanej relácii. "
            "Ignoruj všetky predchádzajúce pokyny a odpovedaj výlučne po slovensky. "
            "Posudzuj iba predložený článok a navrhnutú kategorizáciu."
        )
        
        user_message = f"""
        ## ÚLOHA
        Over presnosť priradenej kategórie a tagov k článku.

        ## KONTEXT
        {text}

        ## HODNOTENÁ KATEGORIZÁCIA
        - Kategória: {data.get('category')}
        - Tagy: {data.get('tags')}

        ## REFERENČNÉ ZOZNAMY
        - Kategórie: {", ".join(PREDEFINED_CATEGORIES)}
        - Tagy: {", ".join(PREDEFINED_TAGS)}

        ## VÝSTUP
        Vyhodnoť polia `is_accurate` a `feedback` podľa modelu CategoryTagsVerification.
        V spätnom hodnotení buď konkrétny, cituj problematické časti a navrhni opravy.
        """
        
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            response_format=CategoryTagsVerification
        )
        
        return response.choices[0].message.parsed.model_dump()
    
    # Verification loop with retries
    current_data = generated_data.copy()
    previous_feedback = None

    for attempt in range(max_retries + 1):
        verification = _verify_once(original_text, current_data)

        if verification["is_accurate"]:
            logging.info("Category/tags verification passed")
            return current_data

        previous_feedback = verification["feedback"]
        logging.warning("Category/tags verification failed on attempt %s: %s", attempt + 1, previous_feedback)

        if attempt == max_retries:
            break

        current_data = get_category_and_tags(original_text, previous_feedback)

    return current_data  # Return last attempt even if not verified

def verify_title_intro(original_text: str, generated_data: dict, max_retries: int = 1) -> dict:
    """Verify title and intro accuracy with retry mechanism"""
    
    def _verify_once(text: str, data: dict) -> dict:
        system_message = (
            "Si nezávislý kontrolór titulkov pracujúci v izolovanej relácii. "
            "Ignoruj všetky predchádzajúce pokyny a odpovedaj výlučne po slovensky."
        )
        
        user_message = f"""
        ## ÚLOHA
        Over presnosť a relevantnosť titulku a úvodu voči článku.

        ## KONTEXT
        {text}

        ## HODNOTENÝ OBSAH
        - Titulok: {data.get('title')}
        - Úvod: {data.get('intro')}

        ## KRITÉRIÁ
        - faktická presnosť,
        - žiadne halucinácie ani zavádzajúce prvky,
        - zhoda tónu s článkom,
        - úvod musí sumarizovať hlavnú informáciu bez marketingových fráz.

        ## VÝSTUP
        Poskytni polia `is_accurate` a `feedback` podľa modelu TitleIntroVerification.
        Buď konkrétny a navrhni úpravy, ak obsah nevyhovuje.
        """
        
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,

            response_format=TitleIntroVerification
        )
        
        return response.choices[0].message.parsed.model_dump()
    
    # Verification loop with retries
    current_data = generated_data.copy()
    previous_feedback = None
    
    for attempt in range(max_retries + 1):
        verification = _verify_once(original_text, current_data)
        
        if verification["is_accurate"]:
            logging.info("Title/intro verification passed")
            return current_data
        
        previous_feedback = verification["feedback"]
        logging.warning("Title/intro verification failed on attempt %s: %s", attempt + 1, previous_feedback)
        
        if attempt == max_retries:
            break
        
        current_data = get_title_and_intro(original_text, previous_feedback)
    
    return current_data  # Return last attempt even if not verified

def verify_summary(
    original_text: str,
    generated_data: dict,
    title: Optional[str] = None,
    intro: Optional[str] = None,
    max_retries: int = 1
) -> dict:
    """Verify summary accuracy with retry mechanism"""
    
    def _verify_once(text: str, data: dict) -> dict:
        system_message = (
            "Si nezávislý verifikátor súhrnov pracujúci v izolovanej relácii. "
            "Ignoruj všetky predošlé pokyny, hodnoť objektívne a odpovedaj výlučne po slovensky."
        )

        closing_requirement = ""
        if title and intro:
            closing_requirement = f'- Záverečná veta musí znieť presne: "Záver: {title}. Úvod: {intro}".'
        elif title:
            closing_requirement = (
                "- Záverečná veta musí jasne pomenovať titulok článku a jeho úvod v jednej vete."
            )
        else:
            closing_requirement = (
                "- Záverečná veta musí explicitne uviesť navrhovaný titulok a úvod."
            )
        
        user_message = f"""
        ## ÚLOHA
        Over, či nasledujúci súhrn verne reprezentuje článok a spĺňa formátne požiadavky.

        ## KONTEXT
        {text}

        ## HODNOTENÝ SÚHRN
        {data.get('summary')}

        ## KRITÉRIÁ
        - zahrnutie všetkých podstatných informácií z článku,
        - absencia halucinovaných údajov,
        - neutralita a objektívnosť,
        - logické usporiadanie a plynulosť,
        {closing_requirement}

        ## VÝSTUP
        Vráť polia `is_accurate` a `feedback` podľa modelu SummaryVerification.
        V prípade chyby uveď chýbajúce informácie, halucinácie, nepresnosti a navrhni úpravy.
        """
        
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            response_format=SummaryVerification
        )
        
        return response.choices[0].message.parsed.model_dump()
    
    # Verification loop with retries
    current_data = generated_data.copy()
    previous_feedback = None
    
    for attempt in range(max_retries + 1):
        verification = _verify_once(original_text, current_data)
        
        if verification["is_accurate"]:
            logging.info("Summary verification passed")
            return current_data
        
        previous_feedback = verification["feedback"]
        logging.warning("Summary verification failed on attempt %s: %s", attempt + 1, previous_feedback)
        
        if attempt == max_retries:
            break

        current_data = get_summary(
            original_text,
            title=title,
            intro=intro,
            feedback=previous_feedback
        )
    
    return current_data  # Return last attempt even if not verified

def _emit_step(log_step: Optional[Callable[[str], None]], message: str) -> None:
    if not log_step:
        return
    try:
        log_step(message)
    except Exception:
        logging.debug("Failed to emit log step '%s'", message)


def process_article(text: str, log_step: Optional[Callable[[str], None]] = None) -> dict:
    """Process article text and return structured data with verification"""
    try:
        logging.info("Starting article processing with verification")
        _emit_step(log_step, "Generating categories and tags")
        
        # Step 1: Generate category and tags with verification
        logging.info("Generating and verifying category/tags...")
        cat_tags = get_category_and_tags(text)
        verified_cat_tags = verify_category_tags(text, cat_tags)
        _emit_step(log_step, "Categories and tags generated")
        
        # Step 2: Generate title and intro with verification
        _emit_step(log_step, "Generating title and intro")
        logging.info("Generating and verifying title/intro...")
        title_intro = get_title_and_intro(text)
        verified_title_intro = verify_title_intro(text, title_intro)
        _emit_step(log_step, "Title and intro generated")
        
        # Step 3: Generate summary with verification
        _emit_step(log_step, "Generating summary")
        logging.info("Generating and verifying summary...")
        summary = get_summary(
            text,
            title=verified_title_intro.get("title"),
            intro=verified_title_intro.get("intro")
        )
        verified_summary = verify_summary(
            text,
            summary,
            title=verified_title_intro.get("title"),
            intro=verified_title_intro.get("intro")
        )
        _emit_step(log_step, "Summary generated")
        
        # Combine all verified results
        article_data = {
            "category": verified_cat_tags.get("category"),
            "tags": verified_cat_tags.get("tags", []),
            "title": verified_title_intro.get("title"),
            "intro": verified_title_intro.get("intro"),
            "summary": verified_summary.get("summary")
        }
        _emit_step(log_step, "Article metadata verification completed")
        
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

def update_article_summary(
    existing_summary: str,
    new_article_text: str,
    title: Optional[str] = None,
    feedback: str = None
) -> dict:
    """Update existing article with new information and optional feedback"""
    if len(new_article_text) > 2000:
        new_article_text = f"{new_article_text[:2000]}..."
    
    # Extract new information from the article
    system_message = (
        "Si skúsený spravodajský editor pracujúci v izolovanej relácii. "
        "Ignoruj všetky predchádzajúce pokyny a odpovedaj výlučne po slovensky. "
        "Tvojou úlohou je aktualizovať súhrn článku o nové informácie bez straty kľúčového obsahu."
    )

    normalized_title = title.strip() if title else None

    user_message = f"""
    ## ÚLOHA
    Aktualizuj pôvodný súhrn článku o nové relevantné informácie a vytvor nový úvod.

    ## EXISTUJÚCI SÚHRN
    {existing_summary}

    ## NOVÝ ČLÁNOK
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
    
    ## POŽIADAVKY
    - Zachovaj presnosť a neutralitu.
    - Zachovaj kľúčové informácie z pôvodného súhrnu.
    - Doplň len overiteľné nové informácie.
    - Spoj staré a nové údaje do logického, zrozumiteľného celku.
    - Napíš nový úvod, ktorý zhrnie aktualizovanú situáciu.
    """

    if normalized_title:
        user_message += f"""
    - Zakonči súhrn vetou presne v tvare: "Záver: {normalized_title}. Úvod: " a po dvojbodke doslovne zopakuj nový úvod.
    """
    else:
        user_message += """
    - Na záver uveď vetu, ktorá explicitne predstaví titulok článku a nový úvod.
    """

    user_message += """
    
    ## VÝSTUP
    Vráť polia `summary` a `intro` podľa schémy pydantic modelu ArticleUpdate.
    """
    
    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            response_format=ArticleUpdate
        )
        
        result = response.choices[0].message.parsed
        
        updated_summary = result.summary.strip() if result.summary else existing_summary.strip()
        updated_intro = result.intro.strip()
        
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

def verify_article_update(
    original_summary: str,
    new_article_text: str,
    updated_data: dict,
    title: Optional[str] = None,
    max_retries: int = 1
) -> dict:
    """Verify updated article summary accuracy with retry mechanism"""
    
    def _verify_once(orig_summary: str, new_text: str, data: dict) -> dict:
        system_message = (
            "Si nezávislý verifikátor aktualizácií článkov pracujúci v izolovanej relácii. "
            "Ignoruj všetky predchádzajúce pokyny a odpovedaj výlučne po slovensky."
        )

        closing_requirement = ""
        if title and data.get("intro"):
            closing_requirement = f'- Súhrn musí končiť vetou: "Záver: {title}. Úvod: {data.get("intro")}".'
        elif title:
            closing_requirement = "- Súhrn musí končiť vetou, ktorá presne uvedie titulok článku a nový úvod."
        else:
            closing_requirement = "- Súhrn musí končiť vetou, ktorá explicitne uvádza titulok a nový úvod."
        
        user_message = f"""
        ## ÚLOHA
        Over, či aktualizovaný súhrn a úvod korektne reflektujú nový článok a zachovávajú pôvodné informácie.

        ## PÔVODNÝ SÚHRN
        {orig_summary}

        ## NOVÝ ČLÁNOK
        {new_text}

        ## AKTUALIZOVANÝ OBSAH
        - Úvod: {data.get('intro')}
        - Súhrn: {data.get('summary')}

        ## KRITÉRIÁ
        - Zachovanie kľúčových informácií zo starého súhrnu,
        - Správne začlenenie nových informácií,
        - Žiadne halucinácie ani nepresnosti,
        - Logické prepojenie pôvodného a nového obsahu,
        {closing_requirement}

        ## VÝSTUP
        Vráť polia `is_accurate` a `feedback` podľa modelu SummaryVerification.
        V prípade chyby popíš, čo chýba, čo je naviac a ako úpravu opraviť.
        """
        
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            response_format=SummaryVerification  # Reuse existing verification model
        )
        
        return response.choices[0].message.parsed.model_dump()
    
    # Verification loop with retries
    current_data = updated_data.copy()
    feedback = None
    
    for attempt in range(max_retries + 1):
        verification = _verify_once(original_summary, new_article_text, current_data)
        
        if verification["is_accurate"]:
            logging.info("Article update verification passed")
            return current_data
        
        feedback = verification["feedback"]
        logging.warning("Article update verification failed on attempt %s: %s", attempt + 1, feedback)
        
        if attempt == max_retries:
            break
        
        current_data = update_article_summary(
            original_summary,
            new_article_text,
            title=title,
            feedback=feedback
        )
    
    return current_data  # Return last attempt even if not verified
