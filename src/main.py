from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
import argparse
from rich.progress import Progress
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional
import re

from . import scraper
from .models import Task, ProposedSolution, OfficialSolution, Evaluation, TaskResult, RunResult
from .llm import evaluate_answer, solve_task, parse_solver_json, available as llm_available


def load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# Fjernet ubrugt TaskResult dataclass


def naive_compare(a: str, b: str) -> float:
    return SequenceMatcher(a=a.lower(), b=b.lower()).ratio()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")

    parser = argparse.ArgumentParser(description="Tænkeboksen – scraper, løsning, evaluering og site-generering")
    parser.add_argument("--out-md", dest="out_md", default=None, help="Gem resultat som Markdown til denne sti")
    parser.add_argument("--out-html", dest="out_html", default=None, help="Gem resultat som HTML-website til denne sti (typisk reports/site/index.html)")
    parser.add_argument("--out-json", dest="out_json", default=None, help="Gem resultat som JSON til denne sti")
    parser.add_argument("--out-csv", dest="out_csv", default=None, help="Gem et fladt CSV-udtræk til denne sti")
    parser.add_argument("--stage", dest="stage", choices=["scrape", "solve", "evaluate", "site", "all"], default="all", help="Kør kun en del: scrape|solve|evaluate|site|all")
    parser.add_argument("--one", dest="one_index", type=int, default=None, help="Kør løsning/evaluering/site kun for opgave med index (1-baseret)")
    parser.add_argument("--limit", dest="limit", type=int, default=120, help="Max antal artikler at overveje fra listings")
    parser.add_argument("--max-pages", dest="max_pages", type=int, default=12, help="Max antal pagination-sider pr. listing")
    parser.add_argument("--cache", dest="cache", default=None, help="Aktivér HTTP-cache (filesystem/sqlite). Eksempel: .cache/http")
    parser.add_argument("--cache-expire", dest="cache_expire", type=int, default=None, help="Cache TTL i sekunder")
    parser.add_argument("--cache-backend", dest="cache_backend", default="filesystem", help="Cache-backend: filesystem eller sqlite (sqlite kan låse ved concurrency)")
    parser.add_argument("--timeout", dest="timeout", type=int, default=20, help="HTTP-timeout i sekunder")
    parser.add_argument("--rate-limit", dest="rate_limit", type=int, default=0, help="Rate limit i millisekunder mellem requests")
    parser.add_argument("--workers", dest="workers", type=int, default=6, help="Antal parallelle hentere for artikler")
    parser.add_argument("--model", dest="model", default=None, help="Overstyr OPENAI_MODEL for denne kørsel")
    parser.add_argument("--log-level", dest="log_level", default="INFO", help="Log-niveau (DEBUG, INFO, WARNING, ERROR)")
    parser.add_argument("--quiet", dest="quiet", action="store_true", help="Undertryk non-kritiske logs")
    parser.add_argument("--no-color", dest="no_color", action="store_true", help="Deaktivér farver i output")
    parser.add_argument("--log-file", dest="log_file", default=None, help="Skriv log til denne fil")
    parser.add_argument("--llm-cache-dir", dest="llm_cache_dir", default=None, help="Cache-mappe til LLM-svar")
    args = parser.parse_args()

    progress_bar = None
    def progress(prefix: str, i: int, n: int) -> None:
        nonlocal progress_bar
        if progress_bar is None:
            progress_bar = Progress() if not args.no_color else Progress(transient=True)
            progress_bar.start()
            progress_bar.add_task(prefix, total=n)
        task_id = progress_bar.task_ids[0]
        progress_bar.update(task_id, completed=i, description=prefix)

    def progress_done() -> None:
        nonlocal progress_bar
        if progress_bar is not None:
            progress_bar.stop()
            progress_bar = None

    # Konfigurer logniveau
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper(), logging.INFO))
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    if args.log_file:
        fh = logging.FileHandler(args.log_file, encoding="utf-8")
        fh.setLevel(logging.getLogger().level)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(fh)

    # Konfigurer scraper
    scraper.configure(
        cache_path=args.cache,
        cache_expire=args.cache_expire,
        cache_backend=args.cache_backend,
        timeout_sec=args.timeout,
        rate_limit_ms=args.rate_limit,
        max_workers=args.workers,
    )

    target_count = 25
    logging.info("Finder %s reelle opgaver med løsning …", target_count)
    # Hent mange Tænkeboksen-artikler (nyeste først)
    raw_articles = scraper.get_latest_taenkeboksen_articles(limit=args.limit, max_pages=args.max_pages, max_workers=args.workers)
    if not raw_articles:
        logging.error("Fandt ingen artikler. Afbryder.")
        return

    # Sekventiel parring: artikel i indeholder typisk løsningen til artikel i+1 (forrige uges opgave)
    filtered_articles: List[scraper.Article] = []
    official_solutions: List[Optional[str]] = []
    task_texts: List[str] = []
    task_numbers: List[Optional[int]] = []

    for idx in range(1, len(raw_articles)):
        art = raw_articles[idx]
        newer_article = raw_articles[idx - 1]

        lower_title = (art.title or "").lower()
        if "lukker og slukker" in lower_title:
            continue

        full_text = scraper.extract_task_text(art.html)
        # Kræv at det ligner en opgave
        if not re.search(r"\bopgave\s*\d+", full_text, flags=re.IGNORECASE):
            continue

        # Byg et nummer->løsning opslag fra den nyere artikel
        sol_map = scraper.extract_solution_map(newer_article.html)
        # Find opgavenummer i denne opgaves fulde tekst
        task_no = scraper.extract_task_number_from_text(full_text)
        sol_text = sol_map.get(task_no) if task_no is not None else None
        if not sol_text:
            # Fallback: forsøg at finde løsning i "Bagsidens svar"-artikler
            try:
                all_svar = scraper.collect_bagsidens_svar_map(max_pages=12)
                if task_no is not None and task_no in all_svar:
                    sol_text = all_svar[task_no][1]
            except Exception:
                sol_text = None
            if not sol_text:
                continue

        filtered_articles.append(art)
        official_solutions.append(sol_text)
        task_texts.append(full_text)
        task_numbers.append(task_no)
        if len(filtered_articles) >= target_count:
            break

    articles = filtered_articles
    if not articles:
        logging.error("Fandt ingen egnede opgaver med tilhørende løsning. Afbryder.")
        return

    # Vi har allerede fuld opgavetekst i task_texts parallelt med articles
    tasks_text: List[str] = task_texts

    # Løsning (afhænger af stage)
    use_llm = llm_available()
    proposed_answers: List[Optional[str]] = [None] * len(articles)
    structured_solutions: List[Optional[dict]] = [None] * len(articles)
    if args.stage in ("solve", "evaluate", "site", "all"):
        if not use_llm:
            logging.info("Ingen LLM-nøgle fundet – springer løsning og LLM-evaluering over.")
        else:
            logging.info("LLM fundet – løser opgaver …")
            run_range = range(len(articles)) if args.one_index is None else range(args.one_index - 1, args.one_index)
            total = len(articles) if args.one_index is None else 1
            done = 0
            for i in run_range:
                try:
                    raw = solve_task(tasks_text[i], model=args.model, cache_dir=args.llm_cache_dir)
                    data = parse_solver_json(raw)
                    if data:
                        structured_solutions[i] = data
                        proposed_answers[i] = data.get("presentation")
                    else:
                        proposed_answers[i] = raw
                except Exception as exc:
                    logging.warning("LLM-fejl ved løsning: %s", exc)
                done += 1
                progress("Solve", done, total)
            progress_done()

    # official_solutions allerede udfyldt i filtreringen

    # Evaluér
    evaluations: List[Optional[str]] = []
    if args.stage in ("evaluate", "site", "all"):
        total_eval = len(articles)
        if llm_available():
            # Paralleliser evaluering let, men bevar rækkefølge
            from concurrent.futures import ThreadPoolExecutor, as_completed
            results_map = {}
            with ThreadPoolExecutor(max_workers=min(6, len(articles))) as ex:
                futures = {}
                for i in range(len(articles)):
                    ans = proposed_answers[i]
                    sol = official_solutions[i]
                    if not ans or not sol:
                        results_map[i] = None
                        continue
                    futures[ex.submit(evaluate_answer, ans, sol, None)] = i
                done_count = 0
                for fut in as_completed(futures):
                    i = futures[fut]
                    try:
                        results_map[i] = fut.result()
                    except Exception as exc:
                        logging.warning("LLM-fejl ved evaluering: %s", exc)
                        results_map[i] = None
                    done_count += 1
                    progress("Evaluate", done_count, total_eval)
            progress_done()
            evaluations = [results_map.get(i) for i in range(len(articles))]
        else:
            for i in range(len(articles)):
                ans = proposed_answers[i]
                sol = official_solutions[i]
                if not ans or not sol:
                    evaluations.append(None)
                else:
                    ratio = naive_compare(ans, sol)
                    evaluations.append(f"Naiv lighed: {ratio:.2f}")
                progress("Evaluate", i + 1, total_eval)
            progress_done()
    else:
        evaluations = [None] * len(articles)

    # Rapportér til terminal og evt. Markdown
    print(f"\n===== Tænkeboksen: {len(articles)} opgaver med løsninger =====\n")

    md_lines: List[str] = []
    html_sections: List[str] = []
    if args.out_md:
        md_lines.append(f"# Tænkeboksen – Opgaver med løsninger")
        md_lines.append("")
        md_lines.append(f"Genereret: {datetime.now().isoformat(timespec='seconds')}")
        md_lines.append("")
    if args.out_html:
        # Build a simple modern HTML shell; sections appended per task
        pass

    for idx, art in enumerate(articles):
        excerpt = (tasks_text[idx] or "").strip()
        opg_nr = task_numbers[idx]

        print(f"{idx+1}. {art.title}")
        print(f"URL: {art.url}")
        print(f"Opgave (fuld tekst):\n{excerpt}\n")

        proposed = proposed_answers[idx]
        if proposed:
            print("Foreslået svar:")
            print(proposed)
        else:
            print("Foreslået svar: (ingen – LLM ikke aktiv)")
        print()

        sol = official_solutions[idx]
        if sol:
            print("Officiel løsning (uddrag):")
            sol_print = sol
            if len(sol_print) > 600:
                sol_print = sol_print[:600] + " …"
            print(sol_print)
        else:
            print("Officiel løsning: (ikke fundet endnu)")
        print()

        eval_text = evaluations[idx]
        if eval_text:
            print(f"Evaluering: {eval_text}")
        else:
            print("Evaluering: (ikke tilgængelig)")
        print("-" * 60)

        if args.out_md:
            if opg_nr is not None:
                md_lines.append(f"## {idx+1}. Opgave {opg_nr} – {art.title}")
            else:
                md_lines.append(f"## {idx+1}. {art.title}")
            md_lines.append(f"**URL**: {art.url}")
            md_lines.append("")
            md_lines.append("**Opgave (fuld tekst):**")
            md_lines.append("")
            md_lines.append("```")
            md_lines.append(excerpt)
            md_lines.append("```")
            md_lines.append("")
            md_lines.append("**Foreslået svar:**")
            md_lines.append("")
            md_lines.append("```")
            md_lines.append(proposed or "(ingen – LLM ikke aktiv)")
            md_lines.append("```")
            md_lines.append("")
            md_lines.append("**Officiel løsning (uddrag):**")
            md_lines.append("")
            md_lines.append("```")
            md_lines.append(sol or "(ikke fundet endnu)")
            md_lines.append("```")
            md_lines.append("")
            md_lines.append("**Evaluering:** " + (eval_text or "(ikke tilgængelig)"))
            md_lines.append("")

        if args.out_html:
            html_sections.append(
                """
                <section class="task">
                  <h2 class="task-title">{idx}. {task_label}</h2>
                  <div class="task-meta"><a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a></div>
                  <div class="block">
                    <h3>Opgave (fuld tekst)</h3>
                    <pre>{excerpt}</pre>
                  </div>
                  <div class="block">
                    <h3>Foreslået svar</h3>
                    <div class="answer">
                      <div class="presentation">{presentation}</div>
                      <details>
                        <summary>Vis trin og mellemregninger</summary>
                        <pre>{details}</pre>
                      </details>
                    </div>
                  </div>
                  <div class="block">
                    <h3>Officiel løsning</h3>
                    <pre>{solution}</pre>
                  </div>
                  <div class="block">
                    <h3>Evaluering</h3>
                    <pre>{evaluation}</pre>
                  </div>
                </section>
                """.format(
                    idx=idx + 1,
                    task_label=(f"Opgave {opg_nr} – {art.title}" if opg_nr is not None else art.title),
                    url=art.url,
                    excerpt=(excerpt or "").replace("<", "&lt;").replace(">", "&gt;"),
                    presentation=(proposed or "(ingen – LLM ikke aktiv)").replace("<", "&lt;").replace(">", "&gt;"),
                    details=(
                        "" if not structured_solutions[idx] else (
                            ("Forståelse: " + str(structured_solutions[idx].get("understanding","")) + "\n\n" +
                             "Klassificering: " + str(structured_solutions[idx].get("classification","")) + "\n\n" +
                             "Data:\n- " + "\n- ".join(structured_solutions[idx].get("data", [])) + "\n\n" +
                             "Metode: " + str(structured_solutions[idx].get("method","")) + "\n\n" +
                             "Trin:\n- " + "\n- ".join(structured_solutions[idx].get("steps", [])) + "\n\n" +
                             "Kontrol: " + str(structured_solutions[idx].get("control",""))
                            ).replace("<","&lt;").replace(">","&gt;")
                        )
                    ),
                    solution=(sol or "(ikke fundet endnu)").replace("<", "&lt;").replace(">", "&gt;"),
                    evaluation=(eval_text or "(ikke tilgængelig)").replace("<", "&lt;").replace(">", "&gt;"),
                )
            )

    # JSON output
    if args.out_json:
        import json
        # Udvidet JSON med datamodeller
        def parse_verdict_and_score(text: Optional[str]) -> tuple[Optional[str], Optional[float]]:
            if not text:
                return None, None
            verdict = None
            if re.search(r"\bMATCH\b", text, re.IGNORECASE):
                verdict = "MATCH"
            if re.search(r"\bNO\s*MATCH\b", text, re.IGNORECASE):
                verdict = "NO MATCH"
            m = re.search(r"score\s*[:=]\s*([01](?:\.\d+)?)", text, re.IGNORECASE)
            score = float(m.group(1)) if m else None
            return verdict, score

        items: list[TaskResult] = []
        for i, art in enumerate(articles):
            verdict, score = parse_verdict_and_score(evaluations[i])
            items.append(
                TaskResult(
                    task=Task(
                        title=art.title,
                        url=art.url,
                        number=task_numbers[i],
                        text=tasks_text[i],
                    ),
                    proposed=ProposedSolution(
                        presentation=proposed_answers[i],
                        structured=structured_solutions[i],
                    ),
                    official=OfficialSolution(text=official_solutions[i]),
                    evaluation=Evaluation(
                        text=evaluations[i], verdict=verdict, score=score
                    ),
                )
            )

        run = RunResult(
            generated_at_iso=datetime.now().isoformat(timespec="seconds"), items=items
        )
        # Serialiser som dict
        def to_dict(obj):
            if isinstance(obj, list):
                return [to_dict(x) for x in obj]
            if hasattr(obj, "__dict__"):
                return {k: to_dict(v) for k, v in obj.__dict__.items()}
            return obj

        payload = to_dict(run)
        out_json_path = Path(args.out_json)
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logging.info("JSON gemt: %s", out_json_path)

    # CSV output
    if args.out_csv:
        import csv
        out_csv_path = Path(args.out_csv)
        out_csv_path.parent.mkdir(parents=True, exist_ok=True)
        with out_csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "idx", "title", "url", "number", "task_excerpt", "answer_presentation", "official_excerpt", "evaluation", "verdict", "score",
            ])
            for i, art in enumerate(articles):
                excerpt = (tasks_text[i] or "").replace("\n", " ")[:800]
                off = (official_solutions[i] or "").replace("\n", " ")[:800]
                verdict, score = (None, None)
                if evaluations[i]:
                    v = None
                    if re.search(r"\bMATCH\b", evaluations[i], re.IGNORECASE):
                        v = "MATCH"
                    if re.search(r"\bNO\s*MATCH\b", evaluations[i], re.IGNORECASE):
                        v = "NO MATCH"
                    m = re.search(r"score\s*[:=]\s*([01](?:\.\d+)?)", evaluations[i], re.IGNORECASE)
                    verdict, score = v, (float(m.group(1)) if m else None)
                writer.writerow([
                    i + 1,
                    art.title,
                    art.url,
                    task_numbers[i] if task_numbers[i] is not None else "",
                    excerpt,
                    proposed_answers[i] or "",
                    off,
                    evaluations[i] or "",
                    verdict or "",
                    (f"{score:.2f}" if score is not None else ""),
                ])
        logging.info("CSV gemt: %s", out_csv_path)

    if args.out_md:
        out_path = Path(args.out_md)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(md_lines), encoding="utf-8")
        logging.info("Markdown rapport gemt: %s", out_path)

    if args.out_html:
        # Prøv Jinja2 template først; fallback til inline HTML hvis template mangler
        logging.info("Bygger HTML website …")
        nav_pills_parts = []
        for i, art in enumerate(articles):
            nr = task_numbers[i]
            label = f"{i+1}. Opgave {nr} – {art.title}" if nr is not None else f"{i+1}. {art.title}"
            nav_pills_parts.append(f"<a class=\"pill\" href=\"#task-{i+1}\">{label}</a>")
        nav_pills = "".join(nav_pills_parts)

        body = "".join(
            section.replace("<section class=\"task\">", f"<section id=\"task-{i+1}\" class=\"task\">")
            for i, section in enumerate(html_sections)
        )

        rendered = None
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape  # type: ignore
            templates_dir = project_root / "reports" / "site_templates"
            env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=select_autoescape(["html"]))
            template = env.get_template("index.html.j2")
            rendered = template.render(
                generated=datetime.now().isoformat(timespec="seconds"),
                nav_pills=nav_pills,
                body=body,
            )
        except Exception:
            rendered = None

        html_parts = [
            "<!doctype html>",
            "<html lang=da>",
            "<head>",
            "  <meta charset=utf-8>",
            "  <meta name=viewport content=\"width=device-width,initial-scale=1\">",
            "  <title>Tænkeboksen – Opgaver med løsninger</title>",
            "  <style>",
            "    :root { --bg:#f8fafc; --card:#ffffff; --text:#0f172a; --muted:#475569; --accent:#0ea5e9; --border:#e2e8f0 }",
            "    body { margin: 0; padding: 0; background: var(--bg); color: var(--text); font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, 'Apple Color Emoji'; }",
            "    .container { max-width: 1100px; margin: 0 auto; padding: 32px 16px; }",
            "    header { margin-bottom: 24px; }",
            "    header h1 { margin: 0 0 6px 0; font-size: 28px; }",
            "    header .subtitle { color: var(--muted); font-size: 14px; }",
            "    .task { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; margin-bottom: 16px; box-shadow: 0 1px 2px rgba(15,23,42,0.06) }",
            "    .task-title { font-size: 20px; margin: 0 0 6px 0; }",
            "    .task-meta a { color: var(--accent); text-decoration: none; word-break: break-all; }",
            "    .block { margin-top: 10px; }",
            "    .block h3 { margin: 0 0 6px 0; font-size: 14px; color: var(--muted); font-weight: 700; letter-spacing:.02em }",
            "    pre { background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; white-space: pre-wrap; word-wrap: break-word; overflow-x: auto; }",
            "    nav { position: sticky; top: 0; backdrop-filter: blur(6px); background: rgba(255,255,255,0.85); border-bottom: 1px solid var(--border); }",
            "    .nav-inner { max-width: 1100px; margin: 0 auto; padding: 8px 16px; display: flex; gap: 10px; overflow-x: auto; }",
            "    .pill { display: inline-block; padding: 6px 10px; border: 1px solid var(--border); border-radius: 999px; color: var(--text); text-decoration: none; font-size: 13px; white-space: nowrap; background:#fff }",
            "    .pill:hover { border-color: var(--accent); color: var(--accent); }",
            "    .answer .presentation { font-weight: 700; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <nav>",
            "    <div class=\"nav-inner\">",
            f"      {nav_pills}",
            "    </div>",
            "  </nav>",
            "  <div class=\"container\">",
            "    <header>",
            "      <h1>Tænkeboksen – Opgaver med løsninger</h1>",
            f"      <div class=\"subtitle\">Genereret {datetime.now().isoformat(timespec='seconds')}</div>",
            "    </header>",
            f"    {body}",
            "  </div>",
            "</body>",
            "</html>",
        ]
        html = rendered if rendered is not None else "\n".join(html_parts)

        out_html_path = Path(args.out_html)
        out_html_path.parent.mkdir(parents=True, exist_ok=True)
        out_html_path.write_text(html, encoding="utf-8")
        logging.info("HTML website gemt: %s", out_html_path)


if __name__ == "__main__":
    main()


