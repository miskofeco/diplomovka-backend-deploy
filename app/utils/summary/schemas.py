from pydantic import BaseModel, Field
from typing import Dict, List


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


class CategoryTagsVerification(BaseModel):
    is_accurate: bool = Field(..., description="Whether the categorization is accurate")
    feedback: str = Field(..., description="Detailed feedback on the categorization")


class TitleIntroVerification(BaseModel):
    is_accurate: bool = Field(..., description="Whether the title and intro are accurate")
    feedback: str = Field(..., description="Detailed feedback on the title and intro")


class SummaryVerification(BaseModel):
    is_accurate: bool = Field(..., description="Whether the summary is accurate and not hallucinated")
    feedback: str = Field(..., description="Detailed feedback on the summary")
