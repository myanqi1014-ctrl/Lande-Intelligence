import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
import html
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# 无需 API 密钥：通过 Google News RSS 采集，通过公开翻译端点翻译。
# 公开翻译端点可能限流或不可用；失败时保留原文并标记，不伪称已翻译。
QUERIES = {
    "沙特": [
        "Saudi Arabia investment manufacturing",
        "Saudi Arabia Chinese companies investment",
        "Saudi Arabia industrial projects",
    ],
    "叙利亚": [
        "Syria investment reconstruction",
        "Syria Chinese companies cooperation",
        "Syria infrastructure projects",
    ],
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LandeIntelligence/1.0)"}
TRANSLATION_ENDPOINT = "https://translate.googleapis.com/translate_a/single"


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def classify(title):
    t = title.lower()
    if any(x in t for x in ("law", "regulation", "policy", "license", "tax")):
        return "投资政策"
    if any(x in t for x in ("china", "chinese")):
        return "中企动态"
    if any(x in t for x in ("project", "construction", "tender", "infrastructure", "reconstruction")):
        return "项目机会"
    return "产业动态"


def translate_zh(text, cache):
    """翻译成简体中文。失败返回原文及 False，不伪装为中文。"""
    if not text:
        return "", True
    if text in cache:
        return cache[text]
    params = urllib.parse.urlencode({
        "client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text
    })
    url = TRANSLATION_ENDPOINT + "?" + params
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.load(response)
        translated = "".join(part[0] for part in data[0] if part and part[0]).strip()
        if not translated:
            raise ValueError("翻译返回空结果")
        result = (translated, True)
    except (OSError, ValueError, TypeError, IndexError, KeyError) as exc:
        print(f"翻译失败（保留原文）: {str(exc)[:120]}")
        result = (text, False)
    cache[text] = result
    return result


def fetch(country, query):
    encoded = urllib.parse.quote(query)
    url = "https://news.google.com/rss/search?q=" + encoded + "&hl=en&gl=US&ceid=US:en"
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        xml_data = response.read()
    root = ET.fromstring(xml_data)
    results = []
    for item in root.findall(".//item")[:15]:
        title = clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        published = item.findtext("pubDate") or ""
        try:
            date_str = parsedate_to_datetime(published).strftime("%Y-%m-%d")
        except (ValueError, TypeError, OverflowError):
            date_str = ""
        source = clean(item.findtext("source")) or "Google News"
        description = clean(item.findtext("description"))
        # Google News 的 description 经常只是重复标题和相关新闻链接；避免误称文章全文摘要。
        if description == title or len(description) < 25:
            description = ""
        if not title or not link.startswith(("https://", "http://")):
            continue
        results.append({
            "country": country,
            "category": classify(title),
            "original_title": title,
            "original_summary": description,
            "date": date_str,
            "source": source,
            "url": link,
        })
    return results


def load_previous():
    if not os.path.exists("news.json"):
        return []
    try:
        with open("news.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("news", []) if isinstance(data.get("news"), list) else []
    except (OSError, ValueError, TypeError) as exc:
        print(f"旧新闻读取失败: {exc}")
        return []


def main():
    previous = load_previous()
    old_by_url = {n.get("url"): n for n in previous if isinstance(n, dict) and n.get("url")}
    articles = []
    seen = set()
    success_feeds = 0
    for country, queries in QUERIES.items():
        for query in queries:
            try:
                found = fetch(country, query)
                success_feeds += 1
                for article in found:
                    key = (article["country"], article["url"])
                    if key not in seen:
                        seen.add(key)
                        articles.append(article)
                print(f"{country}: {query} - {len(found)} 条")
            except Exception as exc:
                print(f"采集失败: {query}: {exc}")

    if not articles:
        print("本次未获取到新闻，保留旧 news.json，不覆盖数据。")
        return

    cache = {}
    news = []
    for article in articles:
        old = old_by_url.get(article["url"], {})
        original_title = article["original_title"]
        original_summary = article["original_summary"]
        if old.get("original_title") == original_title and old.get("translation_status") == "已翻译":
            title = old["title"]
            title_ok = True
        else:
            title, title_ok = translate_zh(original_title, cache)
        if original_summary:
            if old.get("original_summary") == original_summary and old.get("translation_status") == "已翻译":
                summary = old["summary"]
                summary_ok = True
            else:
                summary, summary_ok = translate_zh(original_summary, cache)
        else:
            summary = "RSS 未提供可靠的文章摘要，请查看原文。"
            summary_ok = True
        news.append({
            "country": article["country"],
            "category": article["category"],
            "title": title,
            "date": article["date"],
            "source": article["source"],
            "url": article["url"],
            "summary": summary,
            "original_title": original_title,
            "original_summary": original_summary,
            "translation_status": "已翻译" if title_ok and summary_ok else "翻译失败，保留原文",
            "value": "待研判",
            "action": "待核实新闻内容及招商价值",
        })

    # 保留过去采集的记录，避免“历史归档”随每日运行消失。
    known = {(n["country"], n["url"]) for n in news}
    for old in previous:
        if not isinstance(old, dict):
            continue
        key = (old.get("country"), old.get("url"))
        if key not in known and key[1]:
            news.append(old)
            known.add(key)
    news.sort(key=lambda x: x.get("date", ""), reverse=True)
    # 限制 JSON 文件增长，保留最新 500 条。
    news = news[:500]
    temp = "news.json.tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump({"updated_at": datetime.now(timezone.utc).isoformat(), "news": news}, f, ensure_ascii=False, indent=2)
    os.replace(temp, "news.json")
    print(f"采集完成：{success_feeds} 个新闻源成功，现存 {len(news)} 条新闻")


if __name__ == "__main__":
    main()
