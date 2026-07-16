"""Polite, bounded same-domain crawler.

Deterministic ingestion is deliberately separated from the LLM: the crawler
decides *what exists*, the agent later decides *what it means*. Fetches the
seed page, scores same-domain links by product-relevance keywords, and fetches
the top N. Returns readable text per page.
"""

import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import cfg

UA = "Mozilla/5.0 (partner-scout research bot; contact: recruiter-assignment)"
KEYWORDS = ("product", "solution", "platform", "technology", "about",
            "use-case", "usecase", "feature", "how-it-works", "industries")


def _fetch(url: str, char_limit: int) -> dict | None:
    try:
        r = httpx.get(url, follow_redirects=True, timeout=15,
                      headers={"User-Agent": UA})
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "footer", "nav"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else url
    text = " ".join(soup.get_text(separator=" ").split())[:char_limit]
    links = [urljoin(str(r.url), a["href"]) for a in soup.find_all("a", href=True)]
    return {"url": str(r.url), "title": title, "text": text, "links": links}


def crawl(seed_url: str) -> list[dict]:
    c = cfg()["crawler"]
    max_pages, char_limit = c["max_pages"], c["page_char_limit"]
    delay = c["delay_seconds"]

    seed = _fetch(seed_url, char_limit)
    if seed is None:
        raise RuntimeError(f"could not fetch seed URL {seed_url}")
    domain = urlparse(seed["url"]).netloc
    pages = [seed]

    # rank candidate links: same domain, keyword hits first, dedup, no anchors
    seen = {seed["url"].rstrip("/")}
    candidates = []
    for link in seed["links"]:
        u = link.split("#")[0].rstrip("/")
        if not u or u in seen or urlparse(u).netloc != domain:
            continue
        seen.add(u)
        score = sum(k in u.lower() for k in KEYWORDS)
        candidates.append((score, u))
    candidates.sort(key=lambda t: -t[0])

    for _, u in candidates[: max_pages - 1]:
        time.sleep(delay)
        page = _fetch(u, char_limit)
        if page and len(page["text"]) > 200:      # skip empty/JS-only pages
            pages.append(page)
    for p in pages:
        p.pop("links", None)
    return pages
