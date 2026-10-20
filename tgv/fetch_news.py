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
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TGVIntelligence/1.1)"}
TRANSLATION_ENDPOINT = "https://translate.googleapis.com/translate_a/single"

# Open discovery, not a fixed publisher whitelist:
# Google News RSS is used as a no-key public search index. Site-specific queries are supplementary.
QUERIES = [
    ("Google公开检索·TGV核心英文", '("through-glass via" OR "through glass via" OR "glass via" OR "TGV process" OR "TGV technology")'),
    ("Google公开检索·TGV工艺", '("through-glass via" OR "glass via") (laser drilling OR via formation OR metallization OR copper plating OR via filling)'),
    ("Google公开检索·TGV产业化", '("through-glass via" OR "glass via" OR "TGV process") (production OR qualification OR equipment OR supplier OR patent)'),
    ("Google公开检索·玻璃芯基板通孔", '"glass core substrate" ("through via" OR "via formation" OR TGV OR drilling)'),
    ("Google公开检索·台湾", '(TGV OR "玻璃通孔" OR "玻璃通孔技术" OR "玻璃穿孔") 台湾'),
    ("Google公开检索·中文技术", '("TGV技术" OR "TGV工艺" OR "玻璃通孔" OR "玻璃通孔金属化" OR "玻璃通孔填孔")'),
    ("微信公众号·TGV核心", 'site:mp.weixin.qq.com (TGV OR "玻璃通孔" OR "玻璃通孔技术" OR "TGV工艺")'),
    ("微信公众号·通孔加工", 'site:mp.weixin.qq.com ("玻璃通孔" OR "through-glass via") (激光 OR 钻孔 OR 镀铜 OR 金属化 OR 填孔)'),
    ("微信公众号·玻璃芯基板通孔", 'site:mp.weixin.qq.com ("玻璃芯基板" OR "glass core substrate") (TGV OR 通孔 OR 钻孔)'),
    ("TheElec", 'site:thelec.kr (TGV OR "through-glass via" OR "glass via")'),
    ("Xenospectrum", 'site:xenospectrum.com (TGV OR "through-glass via" OR "glass via")'),
    ("ETNews", 'site:en.etnews.com (TGV OR "through-glass via" OR "glass via")'),
    ("BigGo Finance", 'site:finance.biggo.com (TGV OR "through-glass via" OR "glass via")'),
    ("Seoul Economic Daily", 'site:en.sedaily.com (TGV OR "through-glass via" OR "glass via")'),
    ("学术与专利", '("through-glass via" OR "glass via" OR "TGV process") (research OR patent OR journal)'),
]
DIRECT_TERMS = [
    "through-glass via", "through glass via", "through-glass vias",
    "through glass vias", "glass via", "glass vias",
    "tgv process", "tgv technology", "tgv fabrication", "tgv metallization",
    "tgv drilling", "tgv interposer", "玻璃通孔", "玻璃通孔技术",
    "玻璃通孔工艺", "玻璃通孔金属化", "玻璃通孔填孔", "玻璃穿孔",
    "玻璃通孔加工", "tgv工艺", "tgv技术",
]
GLASS_CORE_TERMS = [
    "glass core substrate via", "glass core substrate vias",
    "glass core via", "玻璃芯基板通孔", "玻璃芯基板通孔加工",
]
PROCESS_TERMS = [
    "laser drilling", "laser ablation", "via metallization", "copper plating",
    "via filling", "via formation", "through via", "microvia",
    "激光钻孔", "激光改质", "通孔金属化", "镀铜", "电镀填孔",
    "通孔填充", "通孔形成", "玻璃通孔加工",
]

def relevance_level(text):
    """Precision-first: only TGV/via-specific stories are admitted."""
    t = text.lower()
    direct = any(k in t for k in DIRECT_TERMS)
    glass_core_via = any(k in t for k in GLASS_CORE_TERMS)
    process = any(k in t for k in PROCESS_TERMS)
    has_glass = "glass" in t or "玻璃" in t
    has_tgv_acronym = re.search(r"\btgv\b", t) is not None or "tgv" in t

    # TGV acronym alone can be ambiguous; require glass/via/process context.
    if has_tgv_acronym and (has_glass or process or "via" in t or "通孔" in t):
        return "直接相关"
    if direct or glass_core_via:
        return "直接相关"
    # Related process stories require explicit glass and via-processing context.
    if has_glass and process and ("via" in t or "通孔" in t or "through" in t):
        return "工艺与设备相关"
    # Generic glass substrate and broad advanced-packaging articles are intentionally excluded.
    return None

def is_relevant(text):
    return relevance_level(text) is not None

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
    if any(k in t for k in ("investment", "funding", "capacity", "fab", "plant", "mass production", "量产", "投资", "产线", "扩产", "融资")):
        return "产业化与投资"
    if any(k in t for k in ("company", "announces", "launch", "supplier", "企业", "公司", "发布", "供应商")):
        return "企业动态"
    return "技术与市场"

def is_relevant(text):
    return relevance_level(text) is not None

def fetch(query_group, query):
    # Google News RSS search endpoint. This is indexed public discovery, not a full crawl of Google Search.
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=zh-CN&gl=TW&ceid=TW:zh-Hant"
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read())
    rows = []
    for item in root.findall(".//item")[:30]:
        original_title = clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if not original_title or not link.startswith(("https://", "http://")):
            continue
        source = clean(item.findtext("source")) or query_group
        summary = clean(item.findtext("description"))
        if summary == original_title or len(summary) < 35:
            summary = ""
        text = original_title + " " + summary
        level = relevance_level(text)
        if not level:
            continue
        rows.append({
            "relevance_level": level,
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
            print(f"{group}: {len(rows)} 条相关结果")
        except Exception as exc:
            print(f"检索失败 [{group}]: {str(exc)[:160]}")

    if not found:
        print("本次没有获取到相关新闻；保留现有数据。")
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
            "relevance": row["relevance_level"] + "：关键词规则初筛通过，仍需人工核验",
            "relevance_level": row["relevance_level"],
        })

    known = {n.get("url") for n in news}
    for old in previous:
        if not isinstance(old, dict) or not old.get("url") or old["url"] in known:
            continue
        searchable = " ".join(str(old.get(k, "")) for k in ("title", "original_title", "summary", "original_summary"))
        level = relevance_level(searchable)
        if level:
            old["relevance_level"] = level
            old["relevance"] = level + "：历史记录通过关键词规则初筛，仍需人工核验"
            news.append(old)
            known.add(old["url"])
    news.sort(key=lambda n: n.get("date", ""), reverse=True)
    news = news[:1000]
    temp = DATA_FILE + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source_queries_succeeded": successes,
            "source_queries_total": len(QUERIES),
            "search_method": "Google News RSS public indexed search; includes broad queries and public WeChat article site queries",
            "news": news
        }, f, ensure_ascii=False, indent=2)
    os.replace(temp, DATA_FILE)
    direct_count = sum(1 for n in news if n.get("relevance_level") == "直接相关")
    related_count = sum(1 for n in news if n.get("relevance_level") == "工艺与设备相关")
    print(f"完成：{successes}/{len(QUERIES)} 个检索成功，归档 {len(news)} 条；直接相关 {direct_count} 条，产业链相关 {related_count} 条。")
    print("说明：微信公众号仅能发现被公开索引的文章；未被索引、需登录或受限制的文章不会保证采集到。")

if __name__ == "__main__":
    main()
