from __future__ import annotations

from pathlib import Path
from src import scraper


def read_fixture(name: str) -> str:
    p = Path(__file__).resolve().parents[1] / "docs" / "text.md"
    # Not a real HTML fixture; sanity check extractors handle generic text
    return p.read_text(encoding="utf-8")


def test_collect_article_links_from_listing_handles_empty():
    assert scraper._collect_article_links_from_listing("") == []


def test_extract_task_number_from_text_none():
    assert scraper.extract_task_number_from_text("ingen opgave her") is None


