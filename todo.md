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
- [ ] Caching af HTML (TTL), konfig via flag/ENV
- [ ] Polite crawling: rate limiting og respekt for 429/Retry-After
- [ ] Smartere pagination-stop (cutoff-dato / 2 tomme sider i træk)

Accept: Kørsel på 10–20 artikler er stabil, hurtig og uden unødige kald.

## 2) Parsing og parring af opgave/løsning
- [ ] Udvid løsning-detektor: også “Facit”, “Svar:”, “Sådan løses…”
- [ ] Kombinér “i+1”-heuristik med `bagsidens svar`-opslag pr. opgavenummer
- [ ] Bedre rensning af brødtekst; fjern nav/footer/relaterede links
- [ ] AMP/Wayback-normalisering; behold original URL i metadata

Accept: ≥90% korrekt parring på et prøveudsæt; manuel spotcheck OK.

## 3) LLM – pålidelighed og evaluering
- [x] Håndhæv JSON-respons (hvor modellen understøtter det)
- [x] Robust JSON-parsing (tåler fenced code og ekstra tekst)
- [ ] CLI `--model` + fallback-kæde; håndter 429 med backoff
- [ ] Parallel `solve`/`evaluate` (rate-limited)
- [x] Evaluator returnerer kort tekst + MATCH/NO MATCH + numerisk score

Accept: ≥95% vellykket parse; evaluatorens dom er stabil ved gentagelser.

## 4) Data- og outputstruktur
- [x] Indfør dataklasser: `Task`, `OfficialSolution`, `ProposedSolution`, `Evaluation`, `RunResult`
- [x] Udvid JSON-output: titel, URL, nr., struktureret svar, evaluering, tidsstempler
- [ ] Flyt HTML til templating (fx Jinja2)
- [ ] Tilføj søgning/filtrering i site (simpel JS)
- [ ] CSV-eksport for flad analyse

Accept: JSON/HTML/CSV er konsistente og dokumenterede.

## 5) CLI og UX
- [ ] Flags: `--limit`, `--since`, `--max-pages`, `--cache`, `--model`, `--rate-limit`, `--log-level`, `--timeout`
- [ ] Progress/logging med `rich`/`tqdm`
- [ ] Forbedr `bagside`: Enter=default run, Ctrl-C håndtering, husk sidste valg
- [ ] `--one` virker også for `evaluate` og `site`

Accept: Hurtig fejlfinding; tydelig feedback; bedre first-run-oplevelse.

## 6) Kvalitet, test og drift
- [ ] Fixtures for HTML; tests for `extract_*` og parring
- [ ] HTTP-mocking (`vcrpy`/`responses`)
- [ ] CI: lint + tests på PR
- [ ] Nightly: scrape/solve/evaluate/site og publicér (fx GitHub Pages)
- [ ] Dockerfile + devcontainer
- [ ] Gem rå HTML ved fejl for nemmere debug

Accept: Grøn CI; stabil nightly; reproducerbare builds.

## 7) Dokumentation
- [ ] Opdatér `README` med nye flags og workflows
- [ ] `CONTRIBUTING.md` (struktur, test, release)
- [ ] Arkitektur-note: dataflow, datamodeller, templating

Accept: Nye bidragydere kan køre projektet på 5 minutter.

---

## Prioritet (først at løse)
- [x] 1. Parallel artikelhentning + Session retries
- [x] 2. Robust LLM-JSON + evaluatorscore
- [x] 3. Udvidet JSON-output + dataklasser
- [ ] 4. Caching + rate limiting

## Seneste status
- 2025-08-10: Initial TODO oprettet.
- 2025-08-10: Løste 1) parallel + retries, 2) robust LLM-JSON + evaluatorscore, 3) udvidet JSON + dataklasser; testet scraping/HTML/JSON.
