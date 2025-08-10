from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover - valgfri dep
    OpenAI = None  # type: ignore


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_prompt(name: str) -> str:
    prompt_path = _project_root() / "prompts" / f"{name}.md"
    return _read_text(prompt_path)


def available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY")) and OpenAI is not None


def solve_task(problem_text: str, model: Optional[str] = None) -> Optional[str]:
    if not available():
        return None

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model_name = model or os.getenv("OPENAI_MODEL", "gpt-5")
    system_prompt = _load_prompt("solver")

    # GPT-5: brug standard temperatur (nogle konfigurationer tillader kun default)
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": problem_text[:8000]},
        ],
        # undlad at sætte temperatur eksplicit
    )
    return (resp.choices[0].message.content or "").strip()


def parse_solver_json(text: Optional[str]) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    import json
    try:
        # prøv at finde første JSON-objekt
        stripped = text.strip()
        # hvis modellen kom til at tilføje ```json fences, fjern dem
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:]
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def evaluate_answer(user_answer: str, official_solution: str, model: Optional[str] = None) -> Optional[str]:
    if not available():
        return None

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model_name = model or os.getenv("OPENAI_MODEL", "gpt-5")
    system_prompt = _load_prompt("evaluator")

    content = (
        f"Brugeren foreslog:\n{user_answer}\n\n"
        f"Officiel løsning:\n{official_solution}\n\n"
        "Vurdér kort om svaret matcher løsningen, og giv en kort begrundelse."
    )

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content[:8000]},
        ],
        # undlad at sætte temperatur eksplicit
    )
    return (resp.choices[0].message.content or "").strip()



