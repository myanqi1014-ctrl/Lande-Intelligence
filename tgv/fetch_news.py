import json
import html
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(ROOT, "news.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TGVIntelligence/1.0)"}
TRANSLATION_ENDPOINT = "https://translate.googleapis.com/translate_a/single"

# Google News RSS query set. Domain-specific queries help surface coverage from the five requested sources.
QUERIES = [
    ("TGV技术", '("Through-Glass Via" OR TGV) glass substrate semiconductor'),
    ("玻璃基板", '"glass core substrate" OR "glass substrate" semiconductor packaging'),
    ("先进封装", '"glass interposer" OR "through glass via" packaging'),
    ("设备与工艺", '"TGV" glass via laser drilling metallization'),
    ("TheElec", 'site:thelec.kr (TGV OR "glass substrate" OR "glass core")'),
    ("Xenospectrum", 'site:xenospectrum.com (TGV OR "glass substrate" OR semiconductor packaging)'),
    ("ETNews", 'site:en.etnews.com (TGV OR "glass substrate" OR "glass core substrate")'),
    ("BigGo Finance", 'site:finance.biggo.com (TGV OR "glass substrate" OR semiconductor packaging)'),
    ("Seoul Economic Daily", 'site:en.sedaily.com (TGV OR "glass substrate" OR semiconductor packaging)'),
    ("台湾科技媒体", '(TGV OR 玻璃基板 OR 玻璃通孔 OR 玻璃芯基板) 台湾 科技'),
    ("中文产业资讯", '(TGV OR 玻璃基板 OR 玻璃通孔) 半导体 封装 产业'),
    ("学术与专利", '("through-glass via" OR "TGV glass substrate") research OR patent'),
]
KEYWORDS = [
    "tgv", "through-glass via", "through glass via", "glass substrate",
    "glass core substrate", "glass interposer", "玻璃通孔", "玻璃基板",
    "玻璃芯基板", "玻璃中介层", "玻璃基封装", "玻璃穿孔",
]

def clean(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()

def translate_zh(text, cache):
    if not text:
        return ""
    if text in cache:
        return cache[text]
    params = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text})
    request = urllib.request.Request(TRANSLATION_ENDPOINT + "?" + params, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.load(response)
        translated = "".join(part[0] for part in data[0] if part and part[0]).strip()
        cache[text] = translated or text
    except Exception as exc:
        print(f"翻译失败，保留原文：{str(exc)[:100]}")
        cache[text] = text
    time.sleep(0.15)
    return cache[text]

def parse_date(value):
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d")
    except (ValueError, TypeError, OverflowError):
        return ""

def category_for(text):
    t = text.lower()
    if any(k in t for k in ("patent", "论文", "research", "研究", "专利", "university", "journal")):
        return "研发与专利"
    if any(k in t for k in ("equipment", "laser", "drilling", "metallization", "设备", "工艺", "加工", "镀铜")):
        return "设备与工艺"
    if any(k in t for k in ("investment", "funding", "capacity", "fab", "plant", "量产", "投资", "产线", "扩产", "融资")):
        return "产业化与投资"
    if any(k in t for k in ("company", "announces", "launch", "supplier", "企业", "公司", "发布", "供应商")):
        return "企业动态"
    return "技术与市场"

def is_relevant(text):
    t = text.lower()
    return any(k in t for k in KEYWORDS)

def fetch(query_group, query):
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=en&gl=US&ceid=US:en"
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read())
    rows = []
    for item in root.findall(".//item")[:20]:
        original_title = clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if not original_title or not link.startswith(("https://", "http://")):
            continue
        source = clean(item.findtext("source")) or query_group
        summary = clean(item.findtext("description"))
        if summary == original_title or len(summary) < 35:
            summary = ""
        text = original_title + " " + summary
        # Domain-specific search results may use synonyms, so keep those results even if the title lacks TGV.
        if not is_relevant(text) and query_group not in {"TheElec", "Xenospectrum", "ETNews", "BigGo Finance", "Seoul Economic Daily", "台湾科技媒体", "中文产业资讯", "学术与专利"}:
            continue
        rows.append({
            "source_group": query_group,
            "original_title": original_title,
            "original_summary": summary,
            "date": parse_date(item.findtext("pubDate") or ""),
            "source": source,
            "url": link,
        })
    return rows

def load_previous():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("news", []) if isinstance(data.get("news"), list) else []
    except (OSError, ValueError, TypeError):
        return []

def main():
    previous = load_previous()
    old_by_url = {n.get("url"): n for n in previous if isinstance(n, dict) and n.get("url")}
    found, seen = [], set()
    successes = 0
    for group, query in QUERIES:
        try:
            rows = fetch(group, query)
            successes += 1
            for row in rows:
                url = row["url"]
                if url not in seen:
                    seen.add(url)
                    found.append(row)
            print(f"{group}: {len(rows)} items")
        except Exception as exc:
            print(f"采集失败 [{group}]: {str(exc)[:160]}")

    if not found:
        print("本次没有获取到新新闻；保留现有数据。")
        return

    cache, news = {}, []
    for row in found:
        old = old_by_url.get(row["url"], {})
        original_title = row["original_title"]
        original_summary = row["original_summary"]
        title = old.get("title") if old.get("original_title") == original_title else None
        if not title:
            title = translate_zh(original_title, cache)
        summary = old.get("summary") if old.get("original_summary") == original_summary and old.get("summary") else None
        if not summary:
            summary = translate_zh(original_summary, cache) if original_summary else "聚合源未提供可靠摘要，请打开原文核实。"
        news.append({
            "title": title,
            "original_title": original_title,
            "summary": summary,
            "original_summary": original_summary,
            "date": row["date"],
            "source": row["source"],
            "source_group": row["source_group"],
            "category": category_for(original_title + " " + original_summary),
            "url": row["url"],
            "translation_status": "自动翻译，建议核对原文" if title != original_title else "保留原文或无需翻译",
            "relevance": "待人工研判",
        })

    known = {n.get("url") for n in news}
    for old in previous:
        if isinstance(old, dict) and old.get("url") and old["url"] not in known:
            news.append(old)
            known.add(old["url"])
    news.sort(key=lambda n: n.get("date", ""), reverse=True)
    news = news[:800]
    temp = DATA_FILE + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump({"updated_at": datetime.now(timezone.utc).isoformat(), "source_queries_succeeded": successes, "news": news}, f, ensure_ascii=False, indent=2)
    os.replace(temp, DATA_FILE)
    print(f"完成：{successes}/{len(QUERIES)} 个检索成功，当前归档 {len(news)} 条。")

if __name__ == "__main__":
    main()
