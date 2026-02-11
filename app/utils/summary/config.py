import os
import json
import logging
import openai
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

SUMMARY_LLM_PROVIDER = os.getenv("SUMMARY_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "openai")).strip().lower()
if SUMMARY_LLM_PROVIDER not in {"openai", "gemini"}:
    logging.warning("Unsupported SUMMARY_LLM_PROVIDER='%s', falling back to 'openai'.", SUMMARY_LLM_PROVIDER)
    SUMMARY_LLM_PROVIDER = "openai"

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
MODEL = OPENAI_MODEL if SUMMARY_LLM_PROVIDER == "openai" else GEMINI_MODEL

API_KEY = os.getenv("OPENAI_API_KEY")
CLIENT = OpenAI(api_key=API_KEY) if API_KEY else None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_CLIENT = None

if SUMMARY_LLM_PROVIDER == "gemini":
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "SUMMARY_LLM_PROVIDER is 'gemini' but GEMINI_API_KEY is missing."
        )
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "google-generativeai package is required for Gemini provider. "
            "Install via `pip install google-generativeai`."
        ) from exc
    genai.configure(api_key=GEMINI_API_KEY)
    GEMINI_CLIENT = genai.GenerativeModel(model_name=GEMINI_MODEL)
elif SUMMARY_LLM_PROVIDER == "openai" and not API_KEY:
    raise RuntimeError(
        "SUMMARY_LLM_PROVIDER is 'openai' but OPENAI_API_KEY is missing."
    )

PREDEFINED_CATEGORIES = [
    "Politika",
    "Ekonomika",
    "Šport",
    "Kultúra",
    "Technológie",
    "Zdravie",
    "Veda",
    "Komentáre",
    "Cestovanie",
    "Blog",
]

PREDEFINED_TAGS = [
    "Trendy",
    "Aktuálne",
    "18+",
    "Krimi",
    "Zaujímavosti",
    "Auto-moto",
    "História",
    "Životný-štyl",
    "Ostatné",
    "Zo sveta",
    "Slovensko",
    "Svet",
    "Európa",
    "Amerika",
    "Ázia",
    "Afrika",
    "Austrália",
    "Pre mladých",
    "Pre Ženy",
    "Pre Študentov",
    "Cirkev",
    "Umelá Inteligencia",
    "IT",
    "Podnikanie",
    "Umenie",
    "Reality-show",
]

POLITICAL_SOURCES = {
    "pravda.sk": "left",
    "aktuality.sk": "neutral",
    "dennikn.sk": "center-left",
    "sme.sk": "center-right",
    "postoj.sk": "right",
}

MAM_DETECTOR_PASSES = int(os.getenv("MAM_DETECTOR_PASSES", "2"))
MAM_CRITIQUE_PASSES = int(os.getenv("MAM_CRITIQUE_PASSES", "2"))
MAM_REFINE_PASSES = int(os.getenv("MAM_REFINE_PASSES", "2"))
MAM_PREFER_CONSISTENT_ON_TIE = os.getenv("MAM_PREFER_CONSISTENT_ON_TIE", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def safe_json(content: object) -> dict:
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        try:
            combined = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in content
            )
            return json.loads(combined)
        except Exception:
            return {}
    try:
        return json.loads(str(content))
    except Exception:
        text = str(content).strip()
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or start >= end:
            return {}
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            return {}


def _gemini_extract_text(response: object) -> str:
    if hasattr(response, "text"):
        text = getattr(response, "text")
        if isinstance(text, str):
            return text
    try:
        return response.candidates[0].content.parts[0].text  # type: ignore[index]
    except Exception:
        return ""


def _gemini_generation_config(temperature: float, as_json: bool = False, schema: dict | None = None):
    import google.generativeai as genai  # type: ignore

    kwargs = {
        "temperature": temperature,
        "max_output_tokens": 4096,
    }
    if as_json:
        kwargs["response_mime_type"] = "application/json"
        if schema:
            kwargs["response_schema"] = schema
    return genai.types.GenerationConfig(**kwargs)


def _render_gemini_prompt(system_message: str, user_message: str, assistant_message: str | None = None) -> str:
    sections = [f"SYSTÉMOVÁ ROLA:\n{system_message}"]
    if assistant_message:
        sections.append(f"KONTEXT ASISTENTA:\n{assistant_message}")
    sections.append(f"POUŽÍVATEĽSKÁ ÚLOHA:\n{user_message}")
    return "\n\n".join(sections)


def generate_text(
    system_message: str,
    user_message: str,
    temperature: float = 0.3,
    assistant_message: str | None = None,
) -> str:
    if SUMMARY_LLM_PROVIDER == "openai":
        if CLIENT is None:
            raise RuntimeError("OpenAI client is not initialized.")
        messages = [{"role": "system", "content": system_message}]
        if assistant_message:
            messages.append({"role": "assistant", "content": assistant_message})
        messages.append({"role": "user", "content": user_message})
        response = CLIENT.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    if GEMINI_CLIENT is None:
        raise RuntimeError("Gemini client is not initialized.")
    prompt = _render_gemini_prompt(system_message, user_message, assistant_message=assistant_message)
    config = _gemini_generation_config(temperature=temperature, as_json=False)
    response = GEMINI_CLIENT.generate_content(prompt, generation_config=config)
    return (_gemini_extract_text(response) or "").strip()


def generate_json(
    system_message: str,
    user_message: str,
    temperature: float = 0.2,
    schema: dict | None = None,
) -> dict:
    if SUMMARY_LLM_PROVIDER == "openai":
        text_response = generate_text(
            system_message=system_message,
            user_message=user_message,
            temperature=temperature,
        )
        return safe_json(text_response)

    if GEMINI_CLIENT is None:
        raise RuntimeError("Gemini client is not initialized.")
    prompt = _render_gemini_prompt(system_message, user_message)
    config = _gemini_generation_config(temperature=temperature, as_json=True, schema=schema)
    response = GEMINI_CLIENT.generate_content(prompt, generation_config=config)
    return safe_json(_gemini_extract_text(response))


def generate_structured(
    system_message: str,
    user_message: str,
    response_model: type[BaseModel],
    temperature: float = 0.3,
    assistant_message: str | None = None,
) -> dict:
    if SUMMARY_LLM_PROVIDER == "openai":
        if CLIENT is None:
            raise RuntimeError("OpenAI client is not initialized.")
        messages = [{"role": "system", "content": system_message}]
        if assistant_message:
            messages.append({"role": "assistant", "content": assistant_message})
        messages.append({"role": "user", "content": user_message})

        response = CLIENT.beta.chat.completions.parse(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
            response_format=response_model,
        )
        parsed = response.choices[0].message.parsed
        return parsed.model_dump()

    # Gemini structured generation with schema validation + one retry.
    schema = response_model.model_json_schema()
    prompt = (
        f"{user_message}\n\n"
        "Vráť výhradne platný JSON podľa schémy. Bez markdownu.\n"
        f"JSON SCHÉMA:\n{json.dumps(schema, ensure_ascii=False)}"
    )
    last_error = None
    for attempt in range(2):
        payload = generate_json(
            system_message=system_message,
            user_message=prompt,
            temperature=temperature,
            schema=schema,
        )
        try:
            return response_model.model_validate(payload).model_dump()
        except ValidationError as exc:
            last_error = str(exc)
            prompt += (
                "\n\nPredchádzajúci JSON nesedel so schémou. Oprav výstup.\n"
                f"Chyby validácie: {last_error}"
            )

    raise RuntimeError(f"Gemini structured output validation failed: {last_error}")
