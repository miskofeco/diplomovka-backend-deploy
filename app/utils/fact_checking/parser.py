import json
import re
from typing import Any, Dict


def safe_json(content: Any) -> Dict[str, Any]:
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
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except Exception:
            return {}
