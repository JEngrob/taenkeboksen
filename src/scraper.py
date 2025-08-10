from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36"
)

_session: Optional[requests.Session] = None

def _get_session() -> requests.Session:
    global _session
    if _session is None:
        sess = requests.Session()
        retry = Retry(
            total=4,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        sess.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        })
        adapter = HTTPAdapter(max_retries=retry)
        sess.mount("https://", adapter)
        sess.mount("http://", adapter)
        _session = sess
    return _session


@dataclass
class Article:
    title: str
    url: str
    html: str


def fetch_url(url: str, timeout: int = 20) -> str:
    response = _get_session().get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def fetch_article_html(url: str) -> str:
    """Hent artikel med fallback til Wayback, hvis der er loginmur/ingen indhold."""
    try:
        html = fetch_url(url)
    except Exception:
        html = ""

    def looks_paywalled(text: str) -> bool:
        if not text:
            return True
        lower = text.lower()
        return ("du skal være logget ind" in lower) or (len(BeautifulSoup(text, "lxml").get_text(" ", strip=True)) < 200)

    if looks_paywalled(html):
        # AMP-fallback
        amp_url = None
        if url.endswith("/amp"):
            amp_url = url
        else:
            if url.endswith("/"):
                amp_url = url + "amp"
            else:
                amp_url = url + "/amp"
        try:
            amp_html = fetch_url(amp_url)
            if not looks_paywalled(amp_html):
                return amp_html
        except Exception:
            pass

    if looks_paywalled(html):
        wb_url = f"https://web.archive.org/web/0/{url}"
        try:
            wb_html = fetch_url(wb_url)
            if not looks_paywalled(wb_html):
                return wb_html
        except Exception:
            pass
    return html


def _collect_article_links_from_listing(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []

    # Generisk udtræk af artikel-links fra en emneside
    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        if not href:
            continue
        # Normalisér relative links
        if href.startswith("/"):
            href = f"https://ing.dk{href}"

        # Kun artikler
        if not href.startswith("https://ing.dk/artikel/"):
            continue

        # Ignorér kommentarankre og dubletter
        if "#" in href:
            href = href.split("#", 1)[0]

        if href not in links:
            links.append(href)

    return links


def _list_article_links_paginated(base_url: str, max_pages: int = 12) -> List[str]:
    """Indsaml artikel-links fra flere paginerede sider.
    Forsøger ?page=1..max_pages. Stopper hvis en side returnerer 0 nye links.
    """
    all_links: List[str] = []
    for page in range(0, max_pages):
        url = base_url if page == 0 else f"{base_url}?page={page}"
        try:
            html = fetch_url(url)
        except Exception:
            continue
        links = _collect_article_links_from_listing(html)
        # Stop hvis ingen nye
        new_links = [l for l in links if l not in all_links]
        if not new_links:
            break
        all_links.extend(new_links)
    return all_links


def _extract_title(soup: BeautifulSoup) -> str:
    # Forsøg via <title>
    if soup.title and soup.title.text.strip():
        return soup.title.text.strip()
    # Fald tilbage til en H1
    h1 = soup.find(["h1", "h1.title"])
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    return "(ukendt titel)"


def extract_main_text(html: str, max_chars: int | None = None) -> str:
    soup = BeautifulSoup(html, "lxml")

    # Prøv at finde hovedindhold (artiklen)
    article = soup.find("article") or soup.find("main") or soup
    paragraphs = [p.get_text(" ", strip=True) for p in article.find_all("p")]
    text = "\n\n".join([p for p in paragraphs if p])
    if max_chars and len(text) > max_chars:
        return text[:max_chars] + " …"
    return text


def _should_drop_line(line: str) -> bool:
    """Filtrér støj og kommentarer fra både opgave- og løsnings-tekst."""
    low = line.strip().lower()
    if not low:
        return False
    drop_substrings = [
        "du skal være logget ind",
        "kommentarsporet",
        "du skal være logget ind for at følge",
        "du skal være logget ind for at følge et emne",
        "del artiklen",
        "annonc",
    ]
    return any(s in low for s in drop_substrings)


def _clean_text_keep_core(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for ln in lines:
        if _should_drop_line(ln):
            continue
        cleaned.append(ln)
    return cleaned


def extract_task_text(html: str) -> str:
    """Udtræk KUN opgaveteksten og undgå boilerplate/kommentarer.

    Stop ved en af grænserne: '– – –', 'Vi bringer løsningen', 'Løsning på opgave'.
    """
    soup = BeautifulSoup(html, "lxml")
    article = soup.find("article") or soup.find("main") or soup

    lines: list[str] = []
    stop = False
    for p in article.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if not txt:
            continue
        low = txt.lower()
        if ("– – –" in txt) or ("vi bringer løsningen" in low) or ("løsning på opgave" in low):
            break
        lines.append(txt)

    lines = _clean_text_keep_core(lines)
    return "\n\n".join(lines)


def extract_solution_section(html: str) -> Optional[str]:
    """
    Find afsnit der ligner "Løsning på opgave …" i en artikel.
    Returnerer ren tekst eller None.
    """
    soup = BeautifulSoup(html, "lxml")
    container = soup.find("article") or soup

    headings = container.find_all(["h2", "h3", "h4"]) or []
    for h in headings:
        title = h.get_text(" ", strip=True).lower()
        if "løsning" in title:  # tidligere krævede vi også "opgave"; tillad bredere match
            # Saml efterfølgende søskende indtil næste overskrift i samme niveau
            solution_parts: List[str] = []
            for sib in h.find_all_next():
                if sib.name in ("h2", "h3", "h4"):
                    break
                if sib.name in ("p", "ul", "ol", "pre", "blockquote"):
                    solution_parts.append(sib.get_text(" ", strip=True))
            text_lines = _clean_text_keep_core([t for t in solution_parts if t])
            text = "\n\n".join(text_lines)
            if text:
                return text
    return None


def extract_solution_sections(html: str) -> List[Tuple[str, str]]:
    """
    Returnér liste af (overskrift, tekst) for alle sektioner, hvor overskriften
    indeholder både "løsning" og "opgave".
    """
    soup = BeautifulSoup(html, "lxml")
    container = soup.find("article") or soup
    results: List[Tuple[str, str]] = []

    # 1) match sektioner hvor overskrift indeholder "løsning"
    headings = container.find_all(["h2", "h3", "h4"]) or []
    for h in headings:
        title = h.get_text(" ", strip=True)
        lower = title.lower()
        if "løsning" in lower:  # tillad bredere match
            parts: List[str] = []
            for sib in h.next_siblings:
                if getattr(sib, "name", None) in ("h2", "h3", "h4"):
                    break
                if getattr(sib, "name", None) in ("p", "ul", "ol", "pre", "blockquote"):
                    parts.append(BeautifulSoup(str(sib), "lxml").get_text(" ", strip=True))
            text = "\n\n".join([t for t in parts if t])
            if text:
                results.append((title, text))

    # 2) fallback: nogle artikler har "Løsning på opgave …" som et afsnit (<p>)
    for p in container.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if not txt:
            continue
        low = txt.lower()
        if "løsning" in low and "opgave" in low:
            # brug dette afsnit som titel og saml efterfølgende afsnit
            title = txt
            parts: List[str] = []
            for sib in p.next_siblings:
                if getattr(sib, "name", None) in ("h2", "h3", "h4"):
                    break
                if getattr(sib, "name", None) == "p":
                    parts.append(sib.get_text(" ", strip=True))
                if getattr(sib, "name", None) in ("ul", "ol", "pre", "blockquote"):
                    parts.append(BeautifulSoup(str(sib), "lxml").get_text(" ", strip=True))
            text_lines = _clean_text_keep_core([t for t in parts if t])
            text = "\n\n".join(text_lines)
            if text:
                results.append((title, text))
    return results


def extract_task_number_from_text(text: str) -> Optional[int]:
    import re
    m = re.search(r"\bopgave\s*(\d+)\b", text, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def extract_solution_map(html: str) -> Dict[int, str]:
    """Byg et opslag: opgavenummer -> løsningstekst fra en artikel.
    Finder både overskrifts- og paragraf-baserede løsningsektioner.
    """
    sections = extract_solution_sections(html)
    number_to_solution: Dict[int, str] = {}
    for heading, text in sections:
        number = extract_task_number_from_text(heading) or extract_task_number_from_text(text[:200])
        if number is not None and text:
            number_to_solution.setdefault(number, text)
    return number_to_solution


def get_latest_taenkeboksen_articles(limit: int = 5) -> List[Article]:
    """Hent de seneste Tænkeboksen-artikler fra ing.dk.

    Strategi:
    1) Prøv emnesiden `emne/taenkeboksen`
    2) Fald tilbage til `fokus/taenkeboksen`
    3) Udtræk artikel-links og hent de første `limit`
    """
    listings = [
        "https://ing.dk/emne/taenkeboksen",
        "https://ing.dk/fokus/taenkeboksen",
    ]

    links: List[str] = []
    for lst_url in listings:
        try:
            paginated_links = _list_article_links_paginated(lst_url, max_pages=12)
            links.extend([l for l in paginated_links if l not in links])
        except Exception as exc:
            logging.warning("Kunne ikke hente listing %s: %s", lst_url, exc)
            continue

    if not links:
        raise RuntimeError("Fandt ingen Tænkeboksen-artikler på ing.dk")

    selected = links[: max(limit, 5)]  # sørg for mindst 5

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _load(url: str) -> Optional[Article]:
        try:
            html = fetch_article_html(url)
            soup = BeautifulSoup(html, "lxml")
            title = _extract_title(soup)
            return Article(title=title, url=url, html=html)
        except Exception as exc:
            logging.error("Fejl ved hentning af artikel %s: %s", url, exc)
            return None

    articles: List[Article] = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_load, url): url for url in selected}
        for fut in as_completed(futures):
            art = fut.result()
            if art is not None:
                articles.append(art)

    return articles


def collect_bagsidens_svar_map(max_pages: int = 20) -> Dict[int, Tuple[Article, str]]:
    """Indsaml et opslag fra opgavenummer -> (artikel, løsningstekst).

    Henter artikler fra både emne- og fokus-siden for "Bagsidens svar" og
    udtrækker alle sektioner, der ligner en løsning. Mapper pr. opgavenummer.
    """
    listings = [
        "https://ing.dk/emne/bagsidens-svar",
        "https://ing.dk/fokus/bagsidens-svar",
    ]

    links: List[str] = []
    for lst_url in listings:
        try:
            paginated_links = _list_article_links_paginated(lst_url, max_pages=max_pages)
            links.extend([l for l in paginated_links if l not in links])
        except Exception as exc:
            logging.warning("Kunne ikke hente listing %s: %s", lst_url, exc)
            continue

    number_to_solution: Dict[int, Tuple[Article, str]] = {}
    import re
    number_re = re.compile(r"opgave\s*(\d+)", re.IGNORECASE)

    for url in links:
        try:
            html = fetch_article_html(url)
            soup = BeautifulSoup(html, "lxml")
            title = _extract_title(soup)
            art = Article(title=title, url=url, html=html)
            sections = extract_solution_sections(html)
            for heading, text in sections:
                m = number_re.search(heading)
                if not m:
                    continue
                n = int(m.group(1))
                number_to_solution.setdefault(n, (art, text))
        except Exception as exc:
            logging.warning("Fejl ved analyse af svarartikel %s: %s", url, exc)
            continue

    return number_to_solution


def find_task_article_for_number(number: int, max_pages: int = 20) -> Optional[Article]:
    """Find opgave-artikel som indeholder 'Opgave <number>'.

    Søger i Tænkeboksen-listerne med pagination. Returnerer første match.
    """
    listings = [
        "https://ing.dk/emne/taenkeboksen",
        "https://ing.dk/fokus/taenkeboksen",
    ]
    import re
    pat = re.compile(rf"\bopgave\s*{number}\b", re.IGNORECASE)

    seen: set[str] = set()
    for lst_url in listings:
        links = _list_article_links_paginated(lst_url, max_pages=max_pages)
        for url in links:
            if url in seen:
                continue
            seen.add(url)
            try:
                html = fetch_article_html(url)
                text = extract_main_text(html, max_chars=None)
                if pat.search(text):
                    soup = BeautifulSoup(html, "lxml")
                    title = _extract_title(soup)
                    return Article(title=title, url=url, html=html)
            except Exception:
                continue
    return None


