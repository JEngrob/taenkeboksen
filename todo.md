# TODO – Bagsiden roadmap

Notation:
- [ ] åbent, [x] løst, [~] i gang
- Et punkt er “Done”, når det er implementeret, testet og dokumenteret.

## 0) Opsætning og housekeeping
- [ ] `.env.example` med `OPENAI_API_KEY` og valgfri `OPENAI_MODEL`
- [ ] Pin afhængigheder eller `pip-tools` for reproducérbarhed
- [ ] Skift til `pyproject.toml` + `console_scripts` for CLI (`bagside`)
- [ ] `pre-commit` med `ruff`, `black`, `mypy` (konfig i repo)

## 1) Scraping – performance og robusthed
- [x] `requests.Session` med retries/backoff og timeouts
- [x] Parallel artikelhentning (IO-bound)
- [x] Caching af HTML (TTL), konfig via flag/ENV (opt-in; default filesystem-backend)
- [x] Polite crawling: rate limiting og respekt for 429/Retry-After (global throttling)
- [x] Smartere pagination-stop (cutoff: 2 tomme sider i træk)

Accept: Kørsel på 10–20 artikler er stabil, hurtig og uden unødige kald.

## 2) Parsing og parring af opgave/løsning
- [x] Udvid løsning-detektor: også “Facit”, “Svar:”, “Sådan løses…”
- [x] Kombinér “i+1”-heuristik med `bagsidens svar`-opslag pr. opgavenummer (fallback)
- [x] Bedre rensning af brødtekst; fjern nav/footer/relaterede links
- [x] AMP/Wayback-normalisering; behold original URL i metadata

Accept: ≥90% korrekt parring på et prøveudsæt; manuel spotcheck OK.

## 3) LLM – pålidelighed og evaluering
- [x] Håndhæv JSON-respons (hvor modellen understøtter det)
- [x] Robust JSON-parsing (tåler fenced code og ekstra tekst)
- [x] CLI `--model` + fallback-kæde; håndter fejlforsøg med backoff
- [x] Parallel `evaluate` (rate-limited via workers)
- [x] Evaluator returnerer kort tekst + MATCH/NO MATCH + numerisk score

Accept: ≥95% vellykket parse; evaluatorens dom er stabil ved gentagelser.

## 4) Data- og outputstruktur
- [x] Indfør dataklasser: `Task`, `OfficialSolution`, `ProposedSolution`, `Evaluation`, `RunResult`
- [x] Udvid JSON-output: titel, URL, nr., struktureret svar, evaluering, tidsstempler
- [ ] Flyt HTML til templating (fx Jinja2)
- [ ] Tilføj søgning/filtrering i site (simpel JS)
- [x] CSV-eksport for flad analyse

Accept: JSON/HTML/CSV er konsistente og dokumenterede.

## 5) CLI og UX
- [x] Flags: `--limit`, `--since`, `--max-pages`, `--cache`, `--cache-backend`, `--cache-expire`, `--model`, `--rate-limit`, `--workers`, `--log-level`, `--timeout`, `--out-csv`
- [x] Progress/logging med `rich`/`tqdm`
- [x] Forbedr `bagside`: Enter=default run, Ctrl-C håndtering, husk sidste valg (CSV-genvej tilføjet)
- [x] `--one` virker også for `evaluate` og `site`

Accept: Hurtig fejlfinding; tydelig feedback; bedre first-run-oplevelse.

## 6) Kvalitet, test og drift
- [ ] Fixtures for HTML; tests for `extract_*` og parring
- [ ] HTTP-mocking (`vcrpy`/`responses`)
- [ ] CI: lint + tests på PR
- [ ] Nightly: scrape/solve/evaluate/site og publicér (fx GitHub Pages)
- [ ] Dockerfile + devcontainer
- [x] Gem rå HTML ved fejl for nemmere debug

Accept: Grøn CI; stabil nightly; reproducerbare builds.

## 7) Dokumentation
- [x] Opdatér `README` med nye flags og workflows
- [ ] `CONTRIBUTING.md` (struktur, test, release)
- [x] Arkitektur-note: dataflow, datamodeller, templating (kort i `docs/overview.md`)

Accept: Nye bidragydere kan køre projektet på 5 minutter.

---

## Prioritet (først at løse)
- [x] 1. Parallel artikelhentning + Session retries
- [x] 2. Robust LLM-JSON + evaluatorscore
- [x] 3. Udvidet JSON-output + dataklasser
- [x] 4. Caching + rate limiting (opt-in cache; default filesystem-backend)
- [x] 5. Forbedringer: CLI-flags, løsning-detektor, fallback-parring, CSV, parallel evaluate

## Seneste status
- 2025-08-10: Initial TODO oprettet.
- 2025-08-10: Løste 1) parallel + retries, 2) robust LLM-JSON + evaluatorscore, 3) udvidet JSON + dataklasser; testet scraping/HTML/JSON.
- 2025-08-10: Løste 4) caching (opt-in) + rate limiting, smartere pagination-stop; udvidede CLI-flags; forbedret løsning-detektor; fallback-parring; CSV; parallel evaluate.
- 2025-08-10: Løste resterende parsing/rensning, rich progress, CSV-menu, paywall-debug dump; dokumentation opdateret.
