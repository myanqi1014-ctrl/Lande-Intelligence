import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
import html
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

QUERIES = {
    "沙特": [
        "Saudi Arabia investment manufacturing",
        "Saudi Arabia Chinese companies investment",
        "Saudi Arabia industrial projects"
    ],
    "叙利亚": [
        "Syria investment reconstruction",
        "Syria Chinese companies cooperation",
        "Syria infrastructure projects"
    ]
}

def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()

def classify(title):
    t = title.lower()

    if any(x in t for x in [
        "law", "regulation", "policy", "license", "tax"
    ]):
        return "投资政策"

    if any(x in t for x in [
        "china", "chinese"
    ]):
        return "中企动态"

    if any(x in t for x in [
        "project", "construction", "tender",
        "infrastructure", "reconstruction"
    ]):
        return "项目机会"

    return "产业动态"

def fetch(country, query):
    encoded = urllib.parse.quote(query)
    url = (
        "https://news.google.com/rss/search?q="
        + encoded
        + "&hl=en&gl=US&ceid=US:en"
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)
    results = []

    for item in root.findall(".//item")[:15]:
        title = clean(item.findtext("title"))
        link = item.findtext("link") or ""
        published = item.findtext("pubDate") or ""

        try:
            date = parsedate_to_datetime(published)
            date_str = date.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            date_str = ""

        source = item.findtext("source") or "Google News"

        if not title or not link:
            continue

        results.append({
            "country": country,
            "category": classify(title),
            "title": title,
            "date": date_str,
            "source": source,
            "url": link,
            "summary": title,
            "value": "待研判",
            "action": "待核实新闻内容及招商价值"
        })

    return results

def main():
    all_news = []
    seen = set()

    for country, queries in QUERIES.items():
        for query in queries:
            try:
                articles = fetch(country, query)

                for article in articles:
                    key = (
                        article["country"],
                        article["title"].lower()
                    )

                    if key not in seen:
                        seen.add(key)
                        all_news.append(article)

                print(f"{country}: {query} - {len(articles)}")

            except Exception as e:
                print(f"采集失败: {query}: {e}")

    all_news.sort(
        key=lambda x: x["date"],
        reverse=True
    )

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "news": all_news
        }, f, ensure_ascii=False, indent=2)

    print(f"采集完成，共 {len(all_news)} 条新闻")

if __name__ == "__main__":
    main()
