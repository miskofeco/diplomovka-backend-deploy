import logging
from typing import List, Optional

from .config import (
    POLITICAL_SOURCES,
    PREDEFINED_CATEGORIES,
    PREDEFINED_TAGS,
    generate_structured,
)
from .mam_refine import (
    collect_critiques,
    detect_inconsistencies,
    generate_baseline_summary,
    refine_summary,
    rerank_summaries,
)
from .prompts import (
    CATEGORY_SYSTEM,
    EVENTS_SYSTEM,
    POLITICAL_SYSTEM,
    TITLE_INTRO_SYSTEM,
    UPDATE_SYSTEM,
)
from .schemas import (
    ArticleUpdate,
    CategoryTags,
    EventsExtraction,
    PoliticalOrientation,
    TitleIntro,
)


def get_category_and_tags(text: str, feedback: str | None = None) -> dict:
    if len(text) > 5000:
        text = text[:5000]

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

    return generate_structured(
        system_message=CATEGORY_SYSTEM,
        user_message=user_message,
        response_model=CategoryTags,
        temperature=0.3,
    )


def get_title_and_intro(text: str, feedback: str | None = None) -> dict:
    if len(text) > 5000:
        text = text[:5000]

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

    return generate_structured(
        system_message=TITLE_INTRO_SYSTEM,
        user_message=user_message,
        response_model=TitleIntro,
        temperature=0.7,
    )


def extract_events(text: str) -> List[str]:
    if len(text) > 5000:
        text = text[:5000]

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
        parsed = generate_structured(
            system_message=EVENTS_SYSTEM,
            user_message=user_message,
            response_model=EventsExtraction,
            temperature=0.2,
        )
        events = parsed.get("events", []) if isinstance(parsed, dict) else []
        return [event.strip() for event in events if isinstance(event, str) and event.strip()]
    except Exception as exc:
        logging.error("Error extracting events: %s", exc)
        return []


def get_summary(
    text: str,
    title: Optional[str] = None,
    intro: Optional[str] = None,
    feedback: str | None = None,
) -> dict:
    if len(text) > 5000:
        text = text[:5000]

    try:
        normalized_title = title.strip() if title else None
        normalized_intro = intro.strip() if intro else None

        if normalized_title and normalized_intro:
            closing_sentence = f"Záver: {normalized_title}. Úvod: {normalized_intro}"
        else:
            closing_sentence = "Záver: [Titulok]. Úvod: [Úvod]"

        baseline_summary, events = generate_baseline_summary(text)
        logging.debug("MAM baseline events: %s", events)
        logging.debug("MAM baseline summary: %s", baseline_summary)
        final_body = baseline_summary

        try:
            sentences, flags = detect_inconsistencies(text, baseline_summary)
            logging.debug("MAM detection flags: %s", flags)

            feedback_lines = collect_critiques(text, baseline_summary, sentences, flags)
            if feedback:
                feedback_lines.append(f"Doplňujúca spätná väzba z verifikácie: {feedback}")

            if feedback_lines:
                feedback_text = "\n\n".join(feedback_lines)
                candidate_summaries = refine_summary(text, baseline_summary, feedback_text)
                final_body = rerank_summaries(text, candidate_summaries)
        except Exception as refine_exc:
            logging.warning("MAM refine phase failed, falling back to baseline summary: %s", refine_exc)

        final_body = final_body.strip()
        if not final_body:
            return {"summary": ""}

        if not final_body.endswith((".", "!", "?")):
            final_body = f"{final_body}."

        summary_with_closing = f"{final_body} {closing_sentence}."
        return {"summary": summary_with_closing}

    except Exception as exc:
        logging.error("Error in get_summary: %s", exc)
        return {"summary": ""}


def analyze_political_orientation(text: str) -> dict:
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

    return generate_structured(
        system_message=POLITICAL_SYSTEM,
        user_message=user_message,
        response_model=PoliticalOrientation,
        temperature=0.2,
    )


def calculate_source_orientation(urls: List[str]) -> dict:
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
            "right_percent": 0,
        }

    return {
        "left_percent": (counts["left"] / total) * 100,
        "center_left_percent": (counts["center-left"] / total) * 100,
        "neutral_percent": (counts["neutral"] / total) * 100,
        "center_right_percent": (counts["center-right"] / total) * 100,
        "right_percent": (counts["right"] / total) * 100,
    }


def update_article_summary(
    existing_summary: str,
    new_article_text: str,
    title: Optional[str] = None,
    feedback: str | None = None,
) -> dict:
    if len(new_article_text) > 2000:
        new_article_text = f"{new_article_text[:2000]}..."

    normalized_title = title.strip() if title else None

    user_message = f"""
    ## ÚLOHA
    Aktualizuj pôvodný súhrn článku o nové relevantné informácie a vytvor nový úvod.

    ## EXISTUJÚCI SÚHRN
    {existing_summary}

    ## NOVÝ ČLÁNOK
    {new_article_text}
    """

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
        result = ArticleUpdate.model_validate(
            generate_structured(
                system_message=UPDATE_SYSTEM,
                user_message=user_message,
                response_model=ArticleUpdate,
                temperature=0.3,
            )
        )

        updated_summary = result.summary.strip() if result.summary else existing_summary.strip()
        updated_intro = result.intro.strip()

        if not updated_intro:
            title_intro = get_title_and_intro(f"{existing_summary}\n\n{new_article_text}", feedback)
            updated_intro = title_intro.get("intro", "")

        return {
            "intro": updated_intro,
            "summary": updated_summary,
        }

    except Exception as exc:
        logging.error("Error updating article summary: %s", exc)
        try:
            title_intro = get_title_and_intro(new_article_text, feedback)
            return {
                "intro": title_intro.get("intro", ""),
                "summary": existing_summary,
            }
        except Exception:
            return {
                "intro": "",
                "summary": existing_summary,
            }
