#!/usr/bin/env python3
"""
Morning Dashboard – Datensammler

Ruft Finanzdaten, Finanznachrichten und Nischen-News ab
und schreibt alles in data.json für die statische Website.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests
import yfinance as yf

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

OUTPUT_FILE = "data.json"
REQUEST_TIMEOUT = 15
YFINANCE_TIMEOUT = 12
MAX_WORKERS = 8
USER_AGENT = "MorningDashboard/1.0 (personal static site; GitHub Actions)"

# yfinance-Ticker: Name, Symbol
INDICES = [
    ("DAX", "^GDAXI"),
    ("S&P 500", "^GSPC"),
    ("Nasdaq", "^IXIC"),
    ("Euro Stoxx 50", "^STOXX50E"),
    ("Nikkei 225", "^N225"),
]

FOREX = [
    ("EUR/USD", "EURUSD=X"),
    ("EUR/GBP", "EURGBP=X"),
    ("EUR/CHF", "EURCHF=X"),
    ("USD/JPY", "JPY=X"),
    ("EUR/JPY", "EURJPY=X"),
]

YIELD_TICKER = ("US 10Y Rendite", "^TNX")

FINANCE_FEEDS = [
    {"name": "FAZ Wirtschaft", "publisher": "FAZ", "url": "https://www.faz.net/rss/aktuell/wirtschaft/"},
    {"name": "Handelsblatt", "publisher": "Handelsblatt", "url": "https://feeds.cms.handelsblatt.com/wirtschaft"},
    {"name": "BBC Business", "publisher": "BBC", "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},
]

# Vielfältige Nischen-Feeds aus Wissenschaft, Forschung, Geschichte, etc.
NICHE_FEEDS = [
    {"name": "ScienceDaily – Gesundheit", "publisher": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/health_medicine.xml", "category": "Medizin"},
    {"name": "ScienceDaily – Neurowissenschaft", "publisher": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/mind_brain.xml", "category": "Neurowissenschaft"},
    {"name": "ScienceDaily – Archäologie", "publisher": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/fossils_ruins.xml", "category": "Archäologie"},
    {"name": "ScienceDaily – Physik", "publisher": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/matter_energy.xml", "category": "Physik"},
    {"name": "Nature News", "publisher": "Nature", "url": "https://www.nature.com/nature.rss", "category": "Forschung"},
    {"name": "NASA Breaking News", "publisher": "NASA", "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss", "category": "Raumfahrt"},
    {"name": "Smithsonian", "publisher": "Smithsonian", "url": "https://www.smithsonianmag.com/rss/science-nature/", "category": "Wissenschaft"},
    {"name": "BBC Future", "publisher": "BBC", "url": "https://www.bbc.com/future/feed.rss", "category": "Zukunft"},
    {"name": "Atlas Obscura", "publisher": "Atlas Obscura", "url": "https://www.atlasobscura.com/feeds/latest", "category": "Entdeckung"},
    {"name": "MIT Technology Review", "publisher": "MIT", "url": "https://www.technologyreview.com/feed/", "category": "Technologie"},
    {"name": "ScienceDaily – Tiere", "publisher": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/plants_animals.xml", "category": "Biologie"},
    {"name": "ScienceDaily – Geowissenschaften", "publisher": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/earth_climate.xml", "category": "Erde"},
]

# Mainstream-Begriffe, die für Nischen-Auswahl depriorisiert werden
MAINSTREAM_KEYWORDS = re.compile(
    r"\b("
    r"trump|biden|election|war|ukraine|gaza|israel|"
    r"stock market|bitcoin price|crypto crash|"
    r"celebrity|kardashian|royal family|"
    r"horoscope|astrology|conspiracy|flat earth|"
    r"miracle cure|anti-vax|5g|chemtrails"
    r")\b",
    re.IGNORECASE,
)

NICHE_ARTICLE_COUNT = 3
FINANCE_ARTICLE_COUNT = 9


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def strip_html(text: str) -> str:
    """Entfernt HTML-Tags und normalisiert Whitespace."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def first_sentence(text: str, max_len: int = 220) -> str:
    """Extrahiert den ersten Satz oder kürzt den Text."""
    text = strip_html(text)
    if not text:
        return ""
    match = re.search(r"^(.+?[.!?])(?:\s|$)", text)
    snippet = match.group(1) if match else text
    if len(snippet) > max_len:
        return snippet[: max_len - 1].rstrip() + "…"
    return snippet


def fetch_url(url: str) -> requests.Response | None:
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        print(f"  [WARN] Request fehlgeschlagen ({url}): {exc}", file=sys.stderr)
        return None


def section_result(data: Any = None, error: str | None = None) -> dict:
    has_data = data is not None and (not isinstance(data, list) or len(data) > 0)
    return {
        "status": "ok" if has_data else "error",
        "error": error,
        "data": data,
    }


# ---------------------------------------------------------------------------
# Finanzdaten
# ---------------------------------------------------------------------------


def fetch_yfinance_quotes(pairs: list[tuple[str, str]]) -> tuple[list[dict], list[str]]:
    """Paralleler Abruf mehrerer yfinance-Ticker mit Timeout pro Symbol."""
    if not pairs:
        return [], []

    items: list[dict] = []
    errors: list[str] = []

    def load_quote(name: str, symbol: str) -> dict | None:
        try:
            hist = yf.Ticker(symbol).history(period="5d", timeout=YFINANCE_TIMEOUT)
            if hist.empty:
                return None
            price = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
            change_pct = None
            if prev_close not in (None, 0):
                change_pct = round(((price - prev_close) / prev_close) * 100, 2)
            return {
                "name": name,
                "symbol": symbol,
                "price": round(price, 4),
                "change_pct": change_pct,
            }
        except Exception as exc:
            print(f"  [WARN] yfinance ({symbol}): {exc}", file=sys.stderr)
            return None

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_map = {
            pool.submit(load_quote, name, symbol): symbol for name, symbol in pairs
        }
        for future in as_completed(future_map):
            symbol = future_map[future]
            try:
                quote_data = future.result()
                if quote_data:
                    items.append(quote_data)
                else:
                    errors.append(symbol)
            except Exception as exc:
                print(f"  [WARN] yfinance future ({symbol}): {exc}", file=sys.stderr)
                errors.append(symbol)

    # Stabile Reihenfolge wie in der Konfiguration
    order = {symbol: idx for idx, (_, symbol) in enumerate(pairs)}
    items.sort(key=lambda item: order.get(item["symbol"], 999))
    return items, errors


def fetch_yfinance_quote(name: str, symbol: str) -> dict | None:
    """Fallback für einzelne Ticker."""
    items, _ = fetch_yfinance_quotes([(name, symbol)])
    return items[0] if items else None


def fetch_indices() -> dict:
    items, errors = fetch_yfinance_quotes(INDICES)

    if not items:
        return section_result(error="Keine Indexdaten verfügbar")
    return section_result(
        data=items,
        error=f"Teilweise nicht verfügbar: {', '.join(errors)}" if errors else None,
    )


def fetch_forex_and_yields() -> dict:
    pairs = FOREX + [YIELD_TICKER]
    items, errors = fetch_yfinance_quotes(pairs)

    for item in items:
        if item["symbol"] == YIELD_TICKER[1]:
            item["unit"] = "%"

    if not items:
        return section_result(error="Keine Wechselkurs-/Zinsdaten verfügbar")
    return section_result(
        data=items,
        error=f"Teilweise nicht verfügbar: {', '.join(errors)}" if errors else None,
    )


def fetch_crypto() -> dict:
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum&vs_currencies=eur,usd&include_24hr_change=true"
    )
    response = fetch_url(url)
    if response is None:
        return section_result(error="CoinGecko nicht erreichbar")

    try:
        payload = response.json()
        mapping = [
            ("Bitcoin", "bitcoin"),
            ("Ethereum", "ethereum"),
        ]
        items = []
        for label, coin_id in mapping:
            coin = payload.get(coin_id, {})
            items.append(
                {
                    "name": label,
                    "symbol": "BTC" if coin_id == "bitcoin" else "ETH",
                    "eur": coin.get("eur"),
                    "usd": coin.get("usd"),
                    "change_24h_pct": round(
                        coin.get("eur_24h_change") or coin.get("usd_24h_change") or 0, 2
                    ) or None,
                }
            )
        return section_result(data=items)
    except (ValueError, KeyError) as exc:
        return section_result(error=f"CoinGecko-Antwort ungültig: {exc}")


# ---------------------------------------------------------------------------
# RSS / News
# ---------------------------------------------------------------------------


def resolve_article_link(entry: dict, feed_url: str) -> str:
    """Bevorzugt den direkten Artikel-Link statt Feed-Aggregator-URLs."""
    for key in ("link", "id"):
        link = entry.get(key, "")
        if link and link.startswith("http"):
            return link

    links = entry.get("links", [])
    for link_obj in links:
        href = link_obj.get("href", "")
        if href.startswith("http") and link_obj.get("rel", "alternate") == "alternate":
            return href

    return feed_url


def parse_feed_entries(feed_meta: dict, max_items: int = 15) -> list[dict]:
    """Parst einen RSS-Feed und liefert normalisierte Artikel."""
    response = fetch_url(feed_meta["url"])
    if response is None:
        return []

    try:
        parsed = feedparser.parse(response.content)
    except Exception as exc:
        print(f"  [WARN] Feed parse ({feed_meta['name']}): {exc}", file=sys.stderr)
        return []

    articles = []
    for entry in parsed.entries[:max_items]:
        title = strip_html(entry.get("title", "")).strip()
        if not title:
            continue

        summary_source = (
            entry.get("summary")
            or entry.get("description")
            or entry.get("content", [{}])[0].get("value", "")
        )
        summary = first_sentence(summary_source)
        link = resolve_article_link(entry, feed_meta["url"])

        articles.append(
            {
                "title": title,
                "summary": summary,
                "link": link,
                "source": feed_meta["name"],
                "publisher": feed_meta.get("publisher", feed_meta["name"]),
                "category": feed_meta.get("category", ""),
            }
        )
    return articles


def fetch_feeds_parallel(feeds: list[dict], max_items: int = 15) -> tuple[list[dict], list[str]]:
    """Ruft mehrere RSS-Feeds parallel ab."""
    results: list[dict] = []
    failed: list[str] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_map = {
            pool.submit(parse_feed_entries, feed, max_items): feed["name"] for feed in feeds
        }
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                articles = future.result()
                if articles:
                    results.extend(articles)
                else:
                    failed.append(name)
            except Exception as exc:
                print(f"  [WARN] Feed future ({name}): {exc}", file=sys.stderr)
                failed.append(name)

    return results, failed


def fetch_finance_news() -> dict:
    all_articles, failed_sources = fetch_feeds_parallel(FINANCE_FEEDS, max_items=6)

    if not all_articles:
        return section_result(error="Finanznachrichten vorübergehend nicht verfügbar")

    # Artikel pro Publisher sammeln und im Round-Robin mischen
    by_publisher: dict[str, list[dict]] = {}
    for article in all_articles:
        publisher = article.get("publisher", article["source"])
        by_publisher.setdefault(publisher, []).append(article)

    publisher_order = [feed["publisher"] for feed in FINANCE_FEEDS]
    seen_titles: set[str] = set()
    unique: list[dict] = []
    max_rounds = 6
    for round_idx in range(max_rounds):
        for publisher in publisher_order:
            articles = by_publisher.get(publisher, [])
            if round_idx >= len(articles):
                continue
            article = articles[round_idx]
            key = article["title"].lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            unique.append(article)
            if len(unique) >= FINANCE_ARTICLE_COUNT:
                break
        if len(unique) >= FINANCE_ARTICLE_COUNT:
            break

    error = None
    if failed_sources:
        error = f"Quellen nicht erreichbar: {', '.join(failed_sources)}"
    return section_result(data=unique, error=error)


def niche_score(article: dict) -> float:
    """Heuristik: höhere Punktzahl = interessanter/nischiger."""
    title = article["title"].lower()
    summary = article.get("summary", "").lower()
    text = f"{title} {summary}"

    score = 0.0

    # Mainstream / unseriöse Themen abwerten
    if MAINSTREAM_KEYWORDS.search(text):
        score -= 50

    # Längere, spezifischere Titel leicht bevorzugen
    score += min(len(title) / 20, 5)

    # Forschungs- und Entdeckungs-Begriffe bevorzugen
    niche_terms = [
        "discover", "found", "study", "research", "genome", "ancient",
        "fossil", "microbe", "neuron", "quantum", "archaeolog", "genetic",
        "species", "ecosystem", "molecule", "telescope", "excavation",
        "entdeck", "forscher", "studie", "gen", "urzeit", "archäolog",
    ]
    for term in niche_terms:
        if term in text:
            score += 2

    # Domains mit viel Allgemeinwissen leicht abwerten
    domain = urlparse(article["link"]).netloc.lower()
    if "sciencedaily.com" in domain:
        score += 1
    if "atlasobscura.com" in domain:
        score += 3

    return score


def daily_seed() -> int:
    """Deterministischer Tages-Seed für reproduzierbare Auswahl."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = hashlib.sha256(today.encode()).hexdigest()
    return int(digest[:8], 16)


def fetch_niche_news() -> dict:
    candidates, failed_sources = fetch_feeds_parallel(NICHE_FEEDS, max_items=8)

    if not candidates:
        return section_result(error="Nischen-News vorübergehend nicht verfügbar")

    # Filtern und nach Nischen-Score sortieren
    filtered = [a for a in candidates if not MAINSTREAM_KEYWORDS.search(a["title"] + " " + a.get("summary", ""))]
    if len(filtered) < NICHE_ARTICLE_COUNT:
        filtered = candidates

    filtered.sort(key=niche_score, reverse=True)

    # Quellenvielfalt sicherstellen: max. 1 Artikel pro Publisher
    selected: list[dict] = []
    used_publishers: set[str] = set()
    seed = daily_seed()

    # Rotierender Startindex für tägliche Variation
    start = seed % max(len(filtered), 1)
    rotated = filtered[start:] + filtered[:start]

    for article in rotated:
        publisher = article.get("publisher") or article["source"]
        if publisher in used_publishers:
            continue
        selected.append(article)
        used_publishers.add(publisher)
        if len(selected) >= NICHE_ARTICLE_COUNT:
            break

    # Fallback: falls zu wenige Quellen, restliche Top-Artikel ergänzen
    if len(selected) < NICHE_ARTICLE_COUNT:
        for article in filtered:
            if article in selected:
                continue
            selected.append(article)
            if len(selected) >= NICHE_ARTICLE_COUNT:
                break

    error = None
    if failed_sources:
        error = f"Quellen nicht erreichbar: {', '.join(failed_sources)}"
    return section_result(data=selected[:NICHE_ARTICLE_COUNT], error=error)


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------


def build_payload() -> dict:
    print("Lade Indexdaten …")
    indices = fetch_indices()

    print("Lade Krypto …")
    crypto = fetch_crypto()

    print("Lade Wechselkurse & Zinsen …")
    markets = fetch_forex_and_yields()

    print("Lade Finanznachrichten …")
    finance_news = fetch_finance_news()

    print("Lade Nischen-News …")
    niche_news = fetch_niche_news()

    return {
        "generated_at": utc_now_iso(),
        "date_label": datetime.now(timezone.utc).strftime("%A, %d. %B %Y"),
        "indices": indices,
        "crypto": crypto,
        "markets": markets,
        "finance_news": finance_news,
        "niche_news": niche_news,
    }


def main() -> int:
    payload = build_payload()
    with open(OUTPUT_FILE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"✓ {OUTPUT_FILE} geschrieben ({payload['generated_at']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
