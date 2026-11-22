"""Precedent leads from Crustdata company news.

News is a LEAD, never evidence: Crustdata's news feed is mostly market and earnings noise, has no way to confirm
what happened on a specific flight, and an article title is not a ruling. Leads are shown to the passenger
labelled "lead, not proof", with date, publisher and link, and never feed the rights engine.
"""
from __future__ import annotations

from typing import Iterable

# Titles that name a consumer dispute or a passenger-rights event. Always a lead.
STRONG = ("consumer commission", "consumer forum", "consumer court", "consumer panel", "consumer disputes",
          "refund", "compensation", "denied boarding", "denial of boarding", "airsewa", "air sewa", "stranded",
          "passenger rights")
# Words that sometimes mean a passenger event: they count only with a flight-related word beside them and
# only when the title is not market chatter. "passenger" and "DGCA" alone are not used: they match traffic
# statistics, fuel surcharges and licence approvals, none of which help a passenger.
WEAK = ("cancel", "delay", "fined", "penalty", "overbooking", "downgrad")
FLIGHT_WORDS = ("flight", "airport", "hour", "hr ", "hrs", "boarding", "baggage")
NOISE = ("share price", "stock", "target price", "shares", "nifty", "sensex", "q1", "q2", "q3", "q4", "quarterly",
         "results", "earnings", "buy rating", "price target", "ipo", "dividend", "esop")

LABEL = "LEAD, NOT PROOF"


def safe_url(url) -> bool:
    """News URLs come from an outside feed and become links: only plain http(s) is allowed (no javascript:, data:)."""
    return isinstance(url, str) and url.strip().lower().startswith(("https://", "http://"))


def classify(title: str) -> list[str]:
    t = (title or "").lower()
    strong = [w for w in STRONG if w in t]
    if strong:
        return strong
    if any(n in t for n in NOISE):
        return []
    if not any(w in t for w in FLIGHT_WORDS):
        return []
    return [w for w in WEAK if w in t]


def extract_leads(news: Iterable[dict], code: str, via: str) -> list[dict]:
    """Keep the news items whose title names a passenger-rights event; newest first, one per URL."""
    seen, out = set(), []
    for n in news or []:
        if not isinstance(n, dict):
            continue
        url, title = n.get("article_url"), n.get("article_title")
        if not url or not title or url in seen or not safe_url(url):
            continue
        matched = classify(title)
        if not matched:
            continue
        seen.add(url)
        out.append({"code": code, "title": title, "url": url, "published": n.get("article_publish_date"),
                    "publisher": n.get("article_publisher_name"), "matched": matched, "via": via, "label": LABEL})
    out.sort(key=lambda x: x["published"] or "", reverse=True)
    return out


def news_from_enrich(payload) -> list[dict]:
    """Pull the news array out of a /company/enrich response."""
    for block in payload or []:
        for m in block.get("matches", []):
            news = (m.get("company_data") or {}).get("news")
            if news:
                return news
    return []


def fetch_company_news(cd, company_id: int) -> list[dict]:
    """On-demand fetch (2 credits, cached 24h, shared by every passenger)."""
    res = cd.post("/company/enrich", {"crustdata_company_ids": [company_id], "fields": ["news"]})
    return news_from_enrich(res.data)

