import logging
import json
from typing import Dict, Optional
import os
from dotenv import load_dotenv

load_dotenv()

# Check if OpenAI is available
openai_api_key = os.getenv("OPENAI_API_KEY")
if openai_api_key:
    try:
        from openai import OpenAI
        from pydantic import BaseModel, Field
        
        client = OpenAI(api_key=openai_api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        openai_available = True
        logging.info("OpenAI client initialized successfully for political analysis")
    except Exception as e:
        logging.error(f"Error initializing OpenAI for political analysis: {e}")
        openai_available = False
        client = None
else:
    logging.warning("OpenAI API key not found, political analysis will be disabled")
    openai_available = False
    client = None

class PoliticalOrientationResponse(BaseModel):
    orientation: str = Field(description="Political orientation: 'left', 'right', or 'neutral'")
    confidence: float = Field(description="Confidence level between 0.0 and 1.0")
    reasoning: str = Field(description="Brief explanation of the analysis")

def analyze_political_orientation(article_text: str) -> Dict[str, any]:
    """
    Analyze the political orientation of an article using OpenAI API
    
    Returns:
    Dict with orientation ('left', 'right', 'neutral'), confidence, and reasoning
    """
    
    if not article_text or len(article_text.strip()) < 50:
        logging.warning("Article text too short for political analysis")
        return {
            "orientation": "neutral",
            "confidence": 0.1,  # Changed from 0.0 to indicate "analyzed but insufficient content"
            "reasoning": "Článok príliš krátky na analýzu politickej orientácie"
        }
    
    if not openai_available or not client:
        logging.warning("OpenAI not available, marking as unanalyzed")
        return {
            "orientation": "neutral",
            "confidence": 0.0,
            "reasoning": "OpenAI API nie je k dispozícii - analýza nevykonaná"
        }
    
    system_message = """Si expertný politický analytik, ktorý dokáže objektívne analyzovať politickú orientáciu článkov.

                        ÚLOHA: Analyzuj politickú orientáciu nasledujúceho článku a klasifikuj ju ako:
                        - "left" (ľavicová) - podporuje progresívne hodnoty, sociálnu spravodlivosť, väčšiu úlohu štátu, práva menšín
                        - "right" (pravicová) - podporuje konzervatívne hodnoty, voľný trh, tradičné hodnoty, menšiu úlohu štátu  
                        - "neutral" (neutrálna) - objektívne spravodajstvo bez jasného politického smerenia

                        KRITÉRIÁ HODNOTENIA:
                        1. Jazyk a tón článku
                        2. Výber faktov a ich prezentácia
                        3. Zdôrazňované témy a hodnoty
                        4. Postoj k vláde, opozícii, inštitúciám
                        5. Framovanie problémov

                        DÔLEŽITÉ:
                        - Buď objektívny a presný
                        - Rozlišuj medzi spravodajstvom a komentármi
                        - Zohľadni slovenský politický kontext
                        - Neutrálne spravodajstvo klasifikuj ako "neutral"
                        - Uvedzi jasný a konkrétny dôvod svojho rozhodnutia"""

    user_message = f"""
                        Analyzuj politickú orientáciu tohto článku:

                        {article_text}

                        Vráť JSON s:
                        - "orientation": "left", "right", alebo "neutral"
                        - "confidence": číslo od 0.0 do 1.0 (0.0 = veľmi neistý, 1.0 = veľmi istý)
                        - "reasoning": konkrétne zdôvodnenie (max 150 znakov, napíš prečo si sa rozhodol tak ako si sa rozhodol)
                        """

    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            response_format=PoliticalOrientationResponse
        )
        
        result = response.choices[0].message.parsed.model_dump()
        
        # Validate orientation value
        if result["orientation"] not in ["left", "right", "neutral"]:
            logging.warning(f"Invalid orientation returned: {result['orientation']}, defaulting to neutral")
            result["orientation"] = "neutral"
            result["reasoning"] = f"Neplatná orientácia '{result['orientation']}', nastavené na neutrálne"
        
        # Ensure confidence is between 0 and 1
        original_confidence = result["confidence"]
        result["confidence"] = max(0.0, min(1.0, result["confidence"]))
        
        # Ensure reasoning is not empty
        if not result["reasoning"] or result["reasoning"].strip() == "":
            result["reasoning"] = f"Orientácia: {result['orientation']}, istota: {result['confidence']:.1f}"
        
        # Truncate reasoning if too long
        if len(result["reasoning"]) > 200:
            result["reasoning"] = result["reasoning"][:197] + "..."
        
        if original_confidence != result["confidence"]:
            logging.warning(f"Confidence adjusted from {original_confidence} to {result['confidence']}")
        
        logging.info(f"Political analysis completed: {result['orientation']} (confidence: {result['confidence']:.2f}) - {result['reasoning'][:50]}...")
        return result
        
    except Exception as e:
        error_msg = f"Chyba pri analýze: {str(e)[:100]}"
        logging.error(f"Error analyzing political orientation: {str(e)}")
        return {
            "orientation": "neutral",
            "confidence": 0.0,
            "reasoning": error_msg
        }

def batch_analyze_political_orientation(articles: list) -> Dict[str, Dict]:
    """
    Analyze political orientation for multiple articles
    
    Args:
        articles: List of dicts with 'url' and 'text' keys
    
    Returns:
        Dict mapping URLs to orientation analysis results
    """
    results = {}
    
    for article in articles:
        url = article.get('url')
        text = article.get('text', '')
        
        if not url:
            continue
            
        logging.info(f"Analyzing political orientation for: {url}")
        
        try:
            analysis = analyze_political_orientation(text)
            results[url] = analysis
        except Exception as e:
            logging.error(f"Failed to analyze {url}: {e}")
            results[url] = {
                "orientation": "neutral",
                "confidence": 0.0,
                "reasoning": f"Analysis failed: {str(e)[:50]}"
            }
    
    return results