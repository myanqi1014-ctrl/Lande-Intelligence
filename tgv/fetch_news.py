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
    # Exact TGV / through-glass-via terms in multiple languages and query styles.
    ("Google·TGV核心英文", '("through-glass via" OR "through glass via" OR "glass via" OR "TGV technology" OR "TGV process")'),
    ("Google·TGV技术研发", '("through-glass via" OR "TGV process") (fabrication OR reliability OR yield OR diameter OR pitch OR aspect ratio)'),
    ("Google·TGV工艺设备", '("through-glass via" OR "glass via") (laser drilling OR laser modification OR metallization OR copper plating OR filling OR equipment)'),
    ("Google·TGV产业化", '("through-glass via" OR "TGV technology") (production OR qualification OR customer OR supplier OR shipment OR factory)'),
    ("Google·TGV专利论文", '("through-glass via" OR "glass via" OR "TGV process") (patent OR paper OR research OR conference)'),
    ("Google·玻璃芯基板", '"glass core substrate" (TGV OR via OR drilling OR metallization OR fabrication)'),
    ("Google·玻璃基板与TGV", '("glass substrate" OR "glass core") ("through-glass via" OR "glass via" OR TGV)'),
    ("Google·Intel玻璃基板", '(Intel OR "glass core substrate") (TGV OR "glass via" OR "through-glass via" OR glass substrate)'),
    ("Google·CoPoS相关", '(CoPoS OR "panel-level packaging") (TGV OR "glass via" OR "glass core substrate")'),
    ("Google·企业与供应商", '("through-glass via" OR "glass core substrate" OR "glass via") (company OR supplier OR equipment OR sample OR qualification)'),
    ("Google·台湾中文", '(TGV OR "玻璃通孔" OR "玻璃穿孔" OR "玻璃芯基板") (制程 OR 钻孔 OR 镀铜 OR 量产 OR 设备) 台湾'),
    ("Google·繁体中文", '(TGV OR 玻璃通孔 OR 玻璃芯基板 OR 玻璃基板) (通孔 OR 雷射 OR 鍍銅 OR 製程 OR 量產)'),
    ("Google·简体中文", '(TGV OR 玻璃通孔 OR 玻璃穿孔 OR 玻璃芯基板) (激光 OR 钻孔 OR 金属化 OR 镀铜 OR 填孔 OR 试产 OR 量产)'),
    ("Google·韩文来源", '(TGV OR "glass via" OR "glass core substrate") semiconductor Korea'),
    ("Google·日文来源", '(TGV OR "through-glass via" OR "glass core substrate") Japan'),
    ("微信公众号·TGV核心", 'site:mp.weixin.qq.com (TGV OR "玻璃通孔" OR "玻璃穿孔" OR "TGV工艺")'),
    ("微信公众号·工艺设备", 'site:mp.weixin.qq.com (TGV OR "玻璃通孔") (激光 OR 钻孔 OR 镀铜 OR 金属化 OR 填孔 OR 设备)'),
    ("微信公众号·玻璃芯基板", 'site:mp.weixin.qq.com ("玻璃芯基板" OR "glass core substrate") (TGV OR 通孔 OR 钻孔 OR 量产)'),
    ("微信公众号·企业动态", 'site:mp.weixin.qq.com (TGV OR "玻璃通孔" OR "玻璃芯基板") (企业 OR 公司 OR 设备 OR 产线 OR 试产 OR 量产)'),
    ("TheElec", 'site:thelec.kr (TGV OR "through-glass via" OR "glass via" OR "glass core substrate")'),
    ("Xenospectrum", 'site:xenospectrum.com (TGV OR "through-glass via" OR "glass via" OR "glass core substrate")'),
    ("ETNews", 'site:en.etnews.com (TGV OR "through-glass via" OR "glass via" OR "glass core substrate")'),
    ("BigGo Finance", 'site:finance.biggo.com (TGV OR "through-glass via" OR "glass via" OR "glass core substrate")'),
    ("Seoul Economic Daily", 'site:en.sedaily.com (TGV OR "through-glass via" OR "glass via" OR "glass core substrate")'),
    ("台湾科技媒体", '(TGV OR "玻璃通孔" OR "玻璃芯基板" OR "glass core substrate") 台湾科技 新闻'),
    ("学术与专利", '("through-glass via" OR "glass via" OR "TGV process") (research OR patent OR journal OR conference)'),
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
    """Precision-first: require explicit TGV/through-via context, not generic packaging terms."""
    t = text.lower()
    exact_via_terms = [
        "through-glass via", "through glass via", "through-glass vias",
        "through glass vias", "glass via", "glass vias",
        "玻璃通孔", "玻璃通孔技术", "玻璃通孔工艺", "玻璃通孔金属化",
        "玻璃通孔填孔", "玻璃穿孔", "玻璃通孔加工",
    ]
    glass_core_via = any(k in t for k in GLASS_CORE_TERMS)
    process = any(k in t for k in PROCESS_TERMS)
    has_glass = "glass" in t or "玻璃" in t
    has_tgv_acronym = re.search(r"\\btgv\\b", t) is not None or "tgv" in t
    has_via_context = any(k in t for k in ("via", "通孔", "through-hole", "through hole", "穿孔"))

    if any(k in t for k in exact_via_terms):
        return "直接相关"
    if has_tgv_acronym and has_glass and has_via_context:
        return "直接相关"
    if has_tgv_acronym and process and has_via_context:
        return "直接相关"
    if glass_core_via and process:
        return "工艺与设备相关"
    if has_glass and process and has_via_context:
        return "工艺与设备相关"
    # Generic glass substrate, semiconductor packaging, company, and market stories are excluded.
    return None

def is_relevant(text):
    return relevance_level(text) is not None

def classify_content(text):
    """Classify TGV-specific articles by the kind of evidence they contain."""
    t = text.lower()
    technical_terms = [
        "process", "fabrication", "laser drilling", "laser ablation",
        "metallization", "copper plating", "via filling", "via formation",
        "aspect ratio", "pitch", "diameter", "yield", "reliability",
        "warpage", "crack", "roughness", "electrical performance",
        "工艺", "制程", "激光钻孔", "激光改质", "金属化", "镀铜",
        "填孔", "孔径", "深宽比", "良率", "可靠性", "翘曲", "裂纹",
        "技术难点", "性能指标", "实验", "验证结果",
    ]
    industrial_terms = [
        "mass production", "production line", "pilot line", "qualification",
        "customer validation", "shipment", "capacity", "equipment order",
        "factory", "plant", "investment", "合作备忘录", "客户验证",
        "送样", "认证", "量产", "试产", "产线", "扩产", "设备采购",
        "建厂", "投产", "产能", "订单", "签约", "合作",
    ]
    market_terms = [
        "market size", "cagr", "market forecast", "market outlook",
        "investment opportunity", "market opportunity", "industry report",
        "market research", "市场规模", "复合年增长率", "市场预测",
        "投资机会", "行业报告", "市场展望", "产业爆发",
    ]
    technical_hits = [k for k in technical_terms if k in t]
    industrial_hits = [k for k in industrial_terms if k in t]
    market_hits = [k for k in market_terms if k in t]

    # Prefer concrete technical evidence, then verifiable industrial milestones.
    if technical_hits:
        return {
            "content_type": "技术进展",
            "quality_reason": "命中具体工艺、性能、可靠性或技术验证词：" + "、".join(technical_hits[:3]),
            "quality_score": min(95, 65 + 5 * len(technical_hits)),
        }
    if industrial_hits and not (market_hits and len(industrial_hits) == 1):
        return {
            "content_type": "产业化进展",
            "quality_reason": "命中产线、试产、客户验证、设备、订单或量产等进展词：" + "、".join(industrial_hits[:3]),
            "quality_score": min(90, 60 + 5 * len(industrial_hits)),
        }
    if market_hits:
        return {
            "content_type": "市场观察",
            "quality_reason": "以市场规模、预测或投资机会为主，缺少明确技术/量产证据",
            "quality_score": 35,
        }
    return {
        "content_type": "待核验",
        "quality_reason": "标题/摘要能确认与 TGV 相关，但暂未识别到明确技术指标或产业化里程碑",
        "quality_score": 45,
    }


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
    for item in root.findall(".//item")[:50]:
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
        quality = classify_content(original_title + " " + original_summary)
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
            "content_type": quality["content_type"],
            "quality_reason": quality["quality_reason"],
            "quality_score": quality["quality_score"],
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
            quality = classify_content(searchable)
            old["content_type"] = quality["content_type"]
            old["quality_reason"] = quality["quality_reason"]
            old["quality_score"] = quality["quality_score"]
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
            "search_method": "Expanded Google News RSS public indexed search: exact TGV terms, technical processes, glass-core substrate TGV, company milestones, Taiwanese/Chinese/Korean/Japanese queries, and public WeChat indexed pages.",
            "news": news
        }, f, ensure_ascii=False, indent=2)
    os.replace(temp, DATA_FILE)
    direct_count = sum(1 for n in news if n.get("relevance_level") == "直接相关")
    related_count = sum(1 for n in news if n.get("relevance_level") == "工艺与设备相关")
    types = {name: sum(1 for n in news if n.get("content_type") == name) for name in ("技术进展", "产业化进展", "市场观察", "待核验")}
    print(f"完成：{successes}/{len(QUERIES)} 个检索成功，归档 {len(news)} 条；直接相关 {direct_count} 条，工艺与设备相关 {related_count} 条。")
    print("内容质量分类：" + "；".join(f"{k} {v} 条" for k, v in types.items()))
    print("说明：微信公众号仅能发现被公开索引的文章；未被索引、需登录或受限制的文章不会保证采集到。")

if __name__ == "__main__":
    main()
