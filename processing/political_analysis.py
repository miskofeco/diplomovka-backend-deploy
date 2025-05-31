import logging
import json
from typing import Dict, Optional
from openai import OpenAI
from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
model = os.getenv("OPENAI_MODEL", "gpt-4")

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
            "confidence": 0.0,
            "reasoning": "Article text too short for analysis"
        }
    
    # Truncate very long articles to avoid token limits
    if len(article_text) > 3000:
        article_text = article_text[:3000] + "..."
    
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
- Uvedzi dôvod svojho rozhodnutia"""

    user_message = f"""
Analyzuj politickú orientáciu tohto článku:

{article_text}

Vráť JSON s:
- "orientation": "left", "right", alebo "neutral"
- "confidence": číslo od 0.0 do 1.0 (0.0 = neistý, 1.0 = veľmi istý)
- "reasoning": krátke zdôvodnenie (max 200 znakov)
"""

    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            max_tokens=500,
            response_format=PoliticalOrientationResponse
        )
        
        result = response.choices[0].message.parsed.model_dump()
        
        # Validate orientation value
        if result["orientation"] not in ["left", "right", "neutral"]:
            logging.warning(f"Invalid orientation returned: {result['orientation']}, defaulting to neutral")
            result["orientation"] = "neutral"
        
        # Ensure confidence is between 0 and 1
        result["confidence"] = max(0.0, min(1.0, result["confidence"]))
        
        logging.info(f"Political analysis: {result['orientation']} (confidence: {result['confidence']:.2f})")
        return result
        
    except Exception as e:
        logging.error(f"Error analyzing political orientation: {str(e)}")
        return {
            "orientation": "neutral",
            "confidence": 0.0,
            "reasoning": f"Analysis failed: {str(e)[:100]}"
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