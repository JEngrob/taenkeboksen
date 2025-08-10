# Contributing


## Setup
- Python 3.10+
- Create venv and install deps:
  - `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Install pre-commit: `pre-commit install`

## Commands
- Run: `python -m src.main --stage all --out-html reports/site/index.html`
- Menu: `./bagside`
- Lint: `ruff check .` and `black --check .`
- Tests: `pytest -q`

## Branch/PR
- Create feature branches; keep PRs small.
- Ensure CI is green (lint+tests) before requesting review.

## Environment
- `.env.example` documents required variables. For LLM features set `OPENAI_API_KEY`.

## Release/Build
- Site build via GitHub Actions nightly; artifacts deployed to Pages.
