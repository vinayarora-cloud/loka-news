import os
import json
import re
import urllib.parse
from datetime import datetime, timezone
import requests
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# Curated reputable feeds spanning regulators, enforcement bodies, and risk domains
FEED_SOURCES = [
    {
        "name": "SEC Press Releases",
        "url": "https://www.sec.gov/news/pressreleases.rss",
        "default_category": "Enforcement Actions"
    },
    {
        "name": "FINRA News & Notices",
        "url": "https://www.finra.org/rss/news",
        "default_category": "Regulatory Change"
    },
    {
        "name": "FCA UK Regulatory News",
        "url": "https://www.fca.org.uk/news/rss.xml",
        "default_category": "Regulatory Change"
    },
    {
        "name": "CFPB Newsroom",
        "url": "https://www.consumerfinance.gov/about-us/newsroom/feed/",
        "default_category": "Enforcement Actions"
    },
    {
        "name": "FTC Enforcement & Privacy",
        "url": "https://www.ftc.gov/news-events/press-releases/feed",
        "default_category": "Data Privacy"
    },
    {
        "name": "CISA Cybersecurity Advisories",
        "url": "https://www.cisa.gov/cybersecurity-advisories/all.xml",
        "default_category": "Cybersecurity Risk"
    },
    {
        "name": "OCC News Releases",
        "url": "https://www.occ.gov/rss/occ_news.xml",
        "default_category": "Operational & Enterprise Risk"
    },
    {
        "name": "ESG Today",
        "url": "https://www.esgtoday.com/feed/",
        "default_category": "ESG & Sustainability"
    },
    {
        "name": "Krebs on Security",
        "url": "https://krebsonsecurity.com/feed/",
        "default_category": "Cybersecurity Risk"
    }
]

# Topic classification keywords
TOPIC_KEYWORDS = {
    "Enforcement Actions": [
        "enforcement", "penalty", "fined", "fine", "sanction", "settlement", 
        "charges", "sued", "guilty", "pleads", "prosecution", "cease and desist", "fraud"
    ],
    "Regulatory Change": [
        "rule", "rulemaking", "regulation", "regulatory", "guidance", "policy", 
        "framework", "compliance date", "standard", "directive", "advisory"
    ],
    "AML & Sanctions": [
        "aml", "anti-money laundering", "sanctions", "ofac", "kyc", "terrorist financing", 
        "illicit finance", "beneficial ownership", "money laundering", "evasion"
    ],
    "Cybersecurity Risk": [
        "cyber", "ransomware", "breach", "malware", "vulnerability", "phishing", 
        "incident", "zero-day", "hacker", "exploit", "cisa"
    ],
    "Data Privacy": [
        "privacy", "gdpr", "ccpa", "personal data", "tracking", "surveillance", 
        "biometric", "data protection", "consent"
    ],
    "ESG & Sustainability": [
        "esg", "climate", "sustainability", "emissions", "carbon", "greenwashing", 
        "scope 3", "net zero", "environmental"
    ],
    "Operational & Enterprise Risk": [
        "operational risk", "enterprise risk", "third-party", "vendor", "resilience", 
        "supply chain", "liquidity", "governance", "whistleblower", "internal control"
    ]
}

def clean_html(text: str) -> str:
    """Strip raw HTML tags, inline styles, and excess whitespace."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    cleaned = soup.get_text(separator=" ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:280] + "..." if len(cleaned) > 280 else cleaned

def normalize_url(url: str) -> str:
    """Normalize URLs by stripping tracking tokens like UTM parameters."""
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return clean_url.rstrip("/")

def parse_entry_date(entry) -> datetime:
    """Extract and parse publication date into a standardized UTC datetime object."""
    raw_date = entry.get("published") or entry.get("updated") or entry.get("created")
    if raw_date:
        try:
            parsed = date_parser.parse(raw_date)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)

def classify_topics(title: str, summary: str, default_cat: str) -> list:
    """Identify relevant risk and compliance topics from article text."""
    combined_text = f"{title} {summary}".lower()
    matched = []
    
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            pattern = rf"\b{re.escape(kw)}\b"
            if re.search(pattern, combined_text):
                matched.append(topic)
                break
                
    if not matched:
        matched.append(default_cat)
    return matched

def fetch_all_feeds():
    articles = []
    seen_links = set()
    seen_titles = set()

    # SEC and government endpoints reject requests without a descriptive User-Agent
    headers = {
        "User-Agent": "LokaNewsAggregator/1.0 (Compliance Desk; contact@lokanews.local)",
        "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"
    }

    for source in FEED_SOURCES:
        source_name = source["name"]
        url = source["url"]
        print(f"Fetching: {source_name}...")

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"  Warning: Received status code {resp.status_code} for {source_name}")
                continue

            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                raw_link = entry.get("link", "").strip()
                link = normalize_url(raw_link)
                raw_title = entry.get("title", "").strip()
                title = clean_html(raw_title)

                # Deduplication across URLs and near-identical titles
                title_key = re.sub(r"[^a-zA-Z0-9]", "", title.lower())
                if not link or link in seen_links or title_key in seen_titles:
                    continue

                seen_links.add(link)
                seen_titles.add(title_key)

                summary = clean_html(entry.get("summary") or entry.get("description", ""))
                pub_date = parse_entry_date(entry)
                topics = classify_topics(title, summary, source["default_category"])

                articles.append({
                    "title": title,
                    "link": raw_link,
                    "source": source_name,
                    "date": pub_date.isoformat(),
                    "display_date": pub_date.strftime("%b %d, %Y"),
                    "summary": summary,
                    "topics": topics
                })
        except Exception as e:
            print(f"  Error loading {source_name}: {e}")

    # Sort descending: newest published items first
    articles.sort(key=lambda x: x["date"], reverse=True)

    # Save to data directory
    os.makedirs("data", exist_ok=True)
    output_path = os.path.join("data", "articles.json")
    
    payload = {
        "last_updated": datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC"),
        "total_count": len(articles),
        "articles": articles
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        
    print(f"Aggregated {len(articles)} unique articles into {output_path}")

if __name__ == "__main__":
    fetch_all_feeds()
