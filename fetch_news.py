import os
import json
import re
import urllib.parse
from datetime import datetime, timezone
import requests
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# Curated feeds: Regulators, Global Outlets, and Australian Mainstream News
FEED_SOURCES = [
    # =========================================================================
    # 1. AUSTRALIAN MAINSTREAM NEWS MEDIA
    # =========================================================================
    # Australian Press Wire Query: AFR, The Australian, SMH, The Age, ABC, SBS, Guardian AU, News.com.au
    {
        "name": "Australian Financial & Mainstream Media",
        "url": "https://news.google.com/rss/search?q=(compliance+OR+regulatory+OR+sanctions+OR+enforcement+OR+%22money+laundering%22+OR+ASIC+OR+APRA+OR+AUSTRAC+OR+ACCC+OR+OAIC+OR+%22cyber+risk%22+OR+penalty)+when:7d+(site:afr.com+OR+site:theaustralian.com.au+OR+site:abc.net.au+OR+site:smh.com.au+OR+site:theage.com.au+OR+site:theguardian.com+OR+site:sbs.com.au+OR+site:news.com.au)&hl=en-AU&gl=AU&ceid=AU:en",
        "default_category": "Regulatory Change",
        "filter_relevance": True
    },
    # ABC News (Australia) - Business Desk
    {
        "name": "ABC News Business (AU)",
        "url": "https://www.abc.net.au/news/feed/51892/rss.xml",
        "default_category": "General Risk",
        "filter_relevance": True
    },
    # The Sydney Morning Herald - Business & Markets
    {
        "name": "The Sydney Morning Herald",
        "url": "https://www.smh.com.au/rss/business.xml",
        "default_category": "General Risk",
        "filter_relevance": True
    },
    # The Age (Melbourne) - Business & Corporate
    {
        "name": "The Age",
        "url": "https://www.theage.com.au/rss/business.xml",
        "default_category": "General Risk",
        "filter_relevance": True
    },
    # The Guardian Australia - Business & Regulation
    {
        "name": "The Guardian Australia",
        "url": "https://www.theguardian.com/au/business/rss",
        "default_category": "General Risk",
        "filter_relevance": True
    },

    # =========================================================================
    # 2. GLOBAL NEWS COMPANIES & FINANCIAL PRESS
    # =========================================================================
    # Global Wires (Reuters, Bloomberg, Financial Times)
    {
        "name": "Global Financial Wire (Reuters / Bloomberg / FT)",
        "url": "https://news.google.com/rss/search?q=(compliance+OR+regulatory+OR+sanctions+OR+enforcement+OR+%22money+laundering%22+OR+SEC+OR+FINRA)+when:7d+(site:reuters.com+OR+site:bloomberg.com+OR+site:ft.com)&hl=en-US&gl=US&ceid=US:en",
        "default_category": "Regulatory Change",
        "filter_relevance": True
    },
    # Wall Street Journal
    {
        "name": "Wall Street Journal",
        "url": "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness",
        "default_category": "General Risk",
        "filter_relevance": True
    },
    # CNBC Business
    {
        "name": "CNBC",
        "url": "https://www.cnbc.com/id/10001147/device/rss/rss.html",
        "default_category": "General Risk",
        "filter_relevance": True
    },

    # =========================================================================
    # 3. GLOBAL & REGIONAL REGULATORY AUTHORITIES
    # =========================================================================
    {
        "name": "SEC Press Releases",
        "url": "https://www.sec.gov/news/pressreleases.rss",
        "default_category": "Enforcement Actions",
        "filter_relevance": False
    },
    {
        "name": "FINRA News & Notices",
        "url": "https://www.finra.org/rss/news",
        "default_category": "Regulatory Change",
        "filter_relevance": False
    },
    {
        "name": "FCA UK Regulatory News",
        "url": "https://www.fca.org.uk/news/rss.xml",
        "default_category": "Regulatory Change",
        "filter_relevance": False
    },
    {
        "name": "CFPB Newsroom",
        "url": "https://www.consumerfinance.gov/about-us/newsroom/feed/",
        "default_category": "Enforcement Actions",
        "filter_relevance": False
    },
    {
        "name": "FTC Enforcement & Privacy",
        "url": "https://www.ftc.gov/news-events/press-releases/feed",
        "default_category": "Data Privacy",
        "filter_relevance": False
    },
    {
        "name": "CISA Cybersecurity Advisories",
        "url": "https://www.cisa.gov/cybersecurity-advisories/all.xml",
        "default_category": "Cybersecurity Risk",
        "filter_relevance": False
    },
    {
        "name": "OCC News Releases",
        "url": "https://www.occ.gov/rss/occ_news.xml",
        "default_category": "Operational & Enterprise Risk",
        "filter_relevance": False
    },

    # =========================================================================
    # 4. SPECIALIZED COMPLIANCE & CYBER MEDIA
    # =========================================================================
    {
        "name": "Compliance Week",
        "url": "https://www.complianceweek.com/feed",
        "default_category": "Regulatory Change",
        "filter_relevance": False
    },
    {
        "name": "Corporate Compliance Insights",
        "url": "https://www.corporatecomplianceinsights.com/feed/",
        "default_category": "Operational & Enterprise Risk",
        "filter_relevance": False
    },
    {
        "name": "Radical Compliance",
        "url": "https://www.radicalcompliance.com/feed/",
        "default_category": "Regulatory Change",
        "filter_relevance": False
    },
    {
        "name": "ESG Today",
        "url": "https://www.esgtoday.com/feed/",
        "default_category": "ESG & Sustainability",
        "filter_relevance": False
    },
    {
        "name": "Krebs on Security",
        "url": "https://krebsonsecurity.com/feed/",
        "default_category": "Cybersecurity Risk",
        "filter_relevance": False
    }
]

# Topic classification keywords (including Australian statutory bodies and terminology)
TOPIC_KEYWORDS = {
    "Enforcement Actions": [
        "enforcement", "penalty", "fined", "fine", "sanction", "settlement", 
        "charges", "sued", "guilty", "pleads", "prosecution", "cease and desist", 
        "fraud", "asic", "accc", "civil penalty", "infringement notice"
    ],
    "Regulatory Change": [
        "rule", "rulemaking", "regulation", "regulatory", "guidance", "policy", 
        "framework", "compliance date", "standard", "directive", "advisory", 
        "regulator", "apra", "cps 230", "cps 234", "prudential standard"
    ],
    "AML & Sanctions": [
        "aml", "anti-money laundering", "sanctions", "ofac", "kyc", "terrorist financing", 
        "illicit finance", "beneficial ownership", "money laundering", "evasion", 
        "austrac", "smr", "dfat"
    ],
    "Cybersecurity Risk": [
        "cyber", "ransomware", "breach", "malware", "vulnerability", "phishing", 
        "incident", "zero-day", "hacker", "exploit", "cisa", "acsc", "asd", 
        "essential eight"
    ],
    "Data Privacy": [
        "privacy", "gdpr", "ccpa", "personal data", "tracking", "surveillance", 
        "biometric", "data protection", "consent", "oaic", "privacy act"
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

def classify_topics(title: str, summary: str, default_cat: str, filter_relevance: bool) -> list:
    """Identify matching risk/compliance topics. Discard unrelated news if filter_relevance is True."""
    combined_text = f"{title} {summary}".lower()
    matched = []
    
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            pattern = rf"\b{re.escape(kw)}\b"
            if re.search(pattern, combined_text):
                matched.append(topic)
                break
                
    if not matched:
        if filter_relevance:
            return []
        matched.append(default_cat)
        
    return matched

def fetch_all_feeds():
    articles = []
    seen_links = set()
    seen_titles = set()

    headers = {
        "User-Agent": "LokaNewsAggregator/1.0 (Compliance Desk; contact@lokanews.local)",
        "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"
    }

    for source in FEED_SOURCES:
        source_name = source["name"]
        url = source["url"]
        filter_relevance = source.get("filter_relevance", False)
        print(f"Fetching: {source_name}...")

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"  Warning: HTTP status {resp.status_code} for {source_name}")
                continue

            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                raw_link = entry.get("link", "").strip()
                link = normalize_url(raw_link)
                raw_title = entry.get("title", "").strip()
                title = clean_html(raw_title)

                # Deduplication across URLs and normalized titles
                title_key = re.sub(r"[^a-zA-Z0-9]", "", title.lower())
                if not link or link in seen_links or title_key in seen_titles:
                    continue

                summary = clean_html(entry.get("summary") or entry.get("description", ""))
                topics = classify_topics(title, summary, source["default_category"], filter_relevance)

                # Skip article if it failed the relevance test for general news outlets
                if filter_relevance and not topics:
                    continue

                seen_links.add(link)
                seen_titles.add(title_key)

                # Extract specific publisher name if available (e.g. from Google News RSS feeds)
                display_source = source_name
                if hasattr(entry, 'source') and hasattr(entry.source, 'title') and entry.source.title:
                    display_source = entry.source.title

                pub_date = parse_entry_date(entry)

                articles.append({
                    "title": title,
                    "link": raw_link,
                    "source": display_source,
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
