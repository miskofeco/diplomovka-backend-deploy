from .config import (
    CLIENT,
    GEMINI_MODEL,
    MODEL,
    OPENAI_MODEL,
    PREDEFINED_CATEGORIES,
    PREDEFINED_TAGS,
    POLITICAL_SOURCES,
    SUMMARY_LLM_PROVIDER,
    generate_json,
    generate_structured,
    generate_text,
)
from .schemas import (
    ArticleSummary,
    ArticleUpdate,
    CategoryTags,
    CategoryTagsVerification,
    EventsExtraction,
    PoliticalOrientation,
    SummaryVerification,
    TitleIntro,
    TitleIntroVerification,
)
from .summary_service import (
    analyze_political_orientation,
    calculate_source_orientation,
    extract_events,
    get_category_and_tags,
    get_summary,
    get_title_and_intro,
    update_article_summary,
)
from .verification import (
    verify_article_update,
    verify_category_tags,
    verify_summary,
    verify_title_intro,
)
from .processing import process_article

# Backward compatibility aliases used by evaluation tooling.
client = CLIENT
model = MODEL

__all__ = [
    "CLIENT",
    "client",
    "MODEL",
    "model",
    "SUMMARY_LLM_PROVIDER",
    "OPENAI_MODEL",
    "GEMINI_MODEL",
    "PREDEFINED_CATEGORIES",
    "PREDEFINED_TAGS",
    "POLITICAL_SOURCES",
    "generate_text",
    "generate_json",
    "generate_structured",
    "ArticleSummary",
    "ArticleUpdate",
    "CategoryTags",
    "CategoryTagsVerification",
    "EventsExtraction",
    "PoliticalOrientation",
    "SummaryVerification",
    "TitleIntro",
    "TitleIntroVerification",
    "analyze_political_orientation",
    "calculate_source_orientation",
    "extract_events",
    "get_category_and_tags",
    "get_summary",
    "get_title_and_intro",
    "update_article_summary",
    "verify_article_update",
    "verify_category_tags",
    "verify_summary",
    "verify_title_intro",
    "process_article",
]
