from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Dict, Any
import hashlib

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


def solve_task(problem_text: str, model: Optional[str] = None, cache_dir: Optional[str] = None) -> Optional[str]:
    if not available():
        return None

    # Init uden proxies-arg (nogle miljøer sætter HTTP(S)_PROXY som konflikter)
    # OpenAI() tager selv OPENAI_API_KEY fra env
    client = OpenAI()
    primary = (model or os.getenv("OPENAI_MODEL") or "gpt-5").strip()
    fallbacks_env = os.getenv("OPENAI_MODEL_FALLBACK", "gpt-4o-mini,gpt-4o").strip()
    model_candidates = [m.strip() for m in ([primary] + fallbacks_env.split(",")) if m.strip()]
    system_prompt = _load_prompt("solver")

    # Disk-cache (opt-in) pr. opgave-tekst
    cache_root = cache_dir or os.getenv("OPENAI_LLM_CACHE")
    cache_path: Optional[Path] = None
    if cache_root:
        try:
            h = hashlib.sha1(problem_text.encode("utf-8")).hexdigest()
            cache_root_path = Path(cache_root)
            cache_root_path.mkdir(parents=True, exist_ok=True)
            cache_path = cache_root_path / f"solve_{h}.txt"
            if cache_path.exists():
                return cache_path.read_text(encoding="utf-8").strip()
        except Exception:
            cache_path = None

    last_err: Optional[Exception] = None
    for mdl in model_candidates:
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=mdl,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": problem_text[:8000]},
                    ],
                    response_format={"type": "json_object"},
                )
                content = (resp.choices[0].message.content or "").strip()
                if cache_path:
                    try:
                        cache_path.write_text(content, encoding="utf-8")
                    except Exception:
                        pass
                return content
            except Exception as e:
                last_err = e
                import time
                time.sleep(0.5 * (2 ** attempt))
        # fallback uden tvunget json-format
        try:
            resp = client.chat.completions.create(
                model=mdl,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": problem_text[:8000]},
                ],
            )
            content = (resp.choices[0].message.content or "").strip()
            if cache_path:
                try:
                    cache_path.write_text(content, encoding="utf-8")
                except Exception:
                    pass
            return content
        except Exception as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("LLM kunne ikke levere svar")


def parse_solver_json(text: Optional[str]) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    import json
    import re
    s = text.strip()
    # Fjern fenced blokke hvis hele indholdet er i ``` ... ```
    if s.startswith("```") and s.endswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.IGNORECASE | re.DOTALL).strip()
    # Scan efter første balancerede {...}
    depth = 0
    start = None
    for i, ch in enumerate(s):
        if ch == "{":
            if start is None:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidate = s[start : i + 1]
                try:
                    obj = json.loads(candidate)
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    start = None
    # sidste forsøg: direkte parse
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def evaluate_answer(user_answer: str, official_solution: str, model: Optional[str] = None) -> Optional[str]:
    if not available():
        return None

    client = OpenAI()
    primary = (model or os.getenv("OPENAI_MODEL") or "gpt-5").strip()
    fallbacks_env = os.getenv("OPENAI_MODEL_FALLBACK", "gpt-4o-mini,gpt-4o").strip()
    model_candidates = [m.strip() for m in ([primary] + fallbacks_env.split(",")) if m.strip()]
    system_prompt = _load_prompt("evaluator")

    content = (
        f"Brugeren foreslog:\n{user_answer}\n\n"
        f"Officiel løsning:\n{official_solution}\n\n"
        "Vurdér kort om svaret matcher løsningen, og giv en kort begrundelse."
    )

    last_err: Optional[Exception] = None
    for mdl in model_candidates:
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=mdl,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content[:8000]},
                    ],
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as e:
                last_err = e
                import time
                time.sleep(0.5 * (2 ** attempt))
    raise last_err if last_err else RuntimeError("LLM evalueringskald fejlede")



