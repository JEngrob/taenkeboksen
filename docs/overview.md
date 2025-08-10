# Bagsiden – GPT‑5 integration (kort overblik)

- Menu: `./bagside`
- Miljø: `.env` med `OPENAI_API_KEY` og evt. `OPENAI_MODEL=gpt-5`.
- Struktureret løsning: `prompts/solver.md` beskriver JSON-krav; `src/llm.py` parser; `src/main.py` bruger `presentation` + accordion.
- Stages: `--stage {scrape|solve|evaluate|site|all}` og `--one N`.
- Nye flags: `--limit`, `--max-pages`, `--cache`, `--cache-backend {filesystem|sqlite}`, `--cache-expire`, `--timeout`, `--rate-limit`, `--workers`, `--model`, `--log-level`, `--out-csv`.
- Cache er opt-in og default er `filesystem` backend (undgår sqlite-låsning ved concurrency).


