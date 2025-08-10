## Bagsiden – Tænkeboksen-skraber og evaluator

Dette værktøj henter de 5 nyeste Tænkeboksen-opgaver fra ing.dk, forsøger at løse dem (valgfrit via LLM), og evaluerer svarene mod publicerede løsninger (typisk vist i den efterfølgende opgaveartikel som "Løsning på opgave …").

### Krav
- Python 3.10+
- `pip` til installation af afhængigheder
- Valgfrit: `OPENAI_API_KEY` i `.env` (kun nødvendig, hvis du vil have LLM til at foreslå løsninger og evaluere dem)

### Installation
```bash
cd /Users/christinaengrob/Kode/Bagsiden
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Opsætning af miljøvariabler
Opret eller rediger `.env` i projektroden:

```
OPENAI_API_KEY=sk-...
# Valgfrit
# OPENAI_MODEL=gpt-4o-mini
```

### Kørsel
```bash
# Aktivér venv
source .venv/bin/activate

# Indlæs .env (macOS/Linux)
export $(grep -v '^#' .env | xargs)

# Kør
python -m src.main

# Gem som Markdown
python -m src.main --out-md reports/latest.md
```

### Hurtig start med menu
Du kan nu starte alt via en simpel menu:

```bash
./bagside
```

Første gang opretter scriptet automatisk `.venv` og installerer dependencies. Menuen giver valg for `scrape`, `solve`, `evaluate`, `site` eller `all`, samt mulighed for at løse en enkelt opgave igen.

Output er en kort rapport i terminalen pr. opgave med:
- Titel og URL
- Kort udtræk af opgavetekst
- Foreslået svar (hvis LLM aktiv)
- "Officiel" løsning udtrukket fra næste artikel (hvis fundet)
- Automatisk vurdering af match (LLM eller simpel tekstsammenligning)

Derudover kan du få en Markdown-rapport i `reports/latest.md`, som indeholder alle felter pr. opgave.

### Noter
- Opgaver hentes fra `https://ing.dk/emne/taenkeboksen` (med fallback til `https://ing.dk/fokus/taenkeboksen`).
- Løsningen til opgave N står typisk i artiklen for opgave N-1 (den nyere artikel). Den nyeste opgave har ofte ingen løsning endnu.
- Strukturen på ing.dk kan ændre sig; mindre justeringer i scraping kan blive nødvendige.

### Licens
MIT


