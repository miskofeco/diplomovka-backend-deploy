import logging
from typing import Optional

from .config import PREDEFINED_CATEGORIES, PREDEFINED_TAGS, generate_structured
from .prompts import (
    CATEGORY_VERIFY_SYSTEM,
    SUMMARY_VERIFY_SYSTEM,
    TITLE_VERIFY_SYSTEM,
    UPDATE_VERIFY_SYSTEM,
)
from .schemas import CategoryTagsVerification, SummaryVerification, TitleIntroVerification
from .summary_service import get_category_and_tags, get_summary, get_title_and_intro, update_article_summary


def verify_category_tags(original_text: str, generated_data: dict, max_retries: int = 1) -> dict:
    def _verify_once(text: str, data: dict) -> dict:
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

        return generate_structured(
            system_message=CATEGORY_VERIFY_SYSTEM,
            user_message=user_message,
            response_model=CategoryTagsVerification,
            temperature=0.1,
        )

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

    return current_data


def verify_title_intro(original_text: str, generated_data: dict, max_retries: int = 1) -> dict:
    def _verify_once(text: str, data: dict) -> dict:
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

        return generate_structured(
            system_message=TITLE_VERIFY_SYSTEM,
            user_message=user_message,
            response_model=TitleIntroVerification,
            temperature=0.3,
        )

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

    return current_data


def verify_summary(
    original_text: str,
    generated_data: dict,
    title: Optional[str] = None,
    intro: Optional[str] = None,
    max_retries: int = 1,
) -> dict:
    def _verify_once(text: str, data: dict) -> dict:
        closing_requirement = ""
        if title and intro:
            closing_requirement = f'- Záverečná veta musí znieť presne: "Záver: {title}. Úvod: {intro}".'
        elif title:
            closing_requirement = "- Záverečná veta musí jasne pomenovať titulok článku a jeho úvod v jednej vete."
        else:
            closing_requirement = "- Záverečná veta musí explicitne uviesť navrhovaný titulok a úvod."

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

        return generate_structured(
            system_message=SUMMARY_VERIFY_SYSTEM,
            user_message=user_message,
            response_model=SummaryVerification,
            temperature=0.3,
        )

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
            feedback=previous_feedback,
        )

    return current_data


def verify_article_update(
    original_summary: str,
    new_article_text: str,
    updated_data: dict,
    title: Optional[str] = None,
    max_retries: int = 1,
) -> dict:
    def _verify_once(orig_summary: str, new_text: str, data: dict) -> dict:
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

        return generate_structured(
            system_message=UPDATE_VERIFY_SYSTEM,
            user_message=user_message,
            response_model=SummaryVerification,
            temperature=0.1,
        )

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
            feedback=feedback,
        )

    return current_data
