import json
import html
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(ROOT, "news.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TGVIntelligence/2.0)"}
TRANSLATION_ENDPOINT = "https://translate.googleapis.com/translate_a/single"

# 仅保留 TGV / 玻璃通孔 / 玻璃芯基板相关检索。
DOMESTIC_QUERIES = [
    ("国内·TGV", '(TGV OR 玻璃通孔 OR 玻璃互连孔 OR 玻璃芯基板 OR 玻璃中介层) 半导体 封装'),
    ("国内·玻璃基板", '("玻璃芯基板" OR "玻璃基板" OR "玻璃中介层") 半导体 先进封装'),
    ("国内·TGV工艺", '(TGV OR 玻璃通孔) (激光 OR 蚀刻 OR 金属化 OR 填孔 OR 电镀 OR 工艺)'),
    ("国内·TGV产业", '(TGV OR 玻璃芯基板) (量产 OR 产线 OR 设备 OR 客户 OR 投资 OR 封装)'),
    ("国内·半导体行业观察", 'site:semiinsights.com (TGV OR 玻璃通孔 OR 玻璃芯基板)'),
    ("国内·爱集微", 'site:ijiwei.com (TGV OR 玻璃通孔 OR 玻璃芯基板 OR 玻璃基板)'),
    ("国内·电子工程专辑", 'site:eet-china.com (TGV OR 玻璃通孔 OR 玻璃芯基板)'),
    ("国内·芯智讯", 'site:icsmart.cn (TGV OR 玻璃通孔 OR 玻璃芯基板)'),
    ("国内·OFweek", 'site:ofweek.com (TGV OR 玻璃通孔 OR 玻璃芯基板)'),
]

FOREIGN_QUERIES = [
    ("国外·TGV", '("through-glass via" OR "through glass via") semiconductor packaging'),
    ("国外·GlassCore", '("glass core substrate" OR "glass-core substrate") semiconductor packaging'),
    ("国外·GlassInterposer", '("glass interposer" OR "glass substrate") (semiconductor OR packaging OR interconnect)'),
    ("国外·TGVProcess", '("through-glass via" OR "glass core substrate") (laser drilling OR etching OR metallization OR plating OR fabrication)'),
    ("国外·TGVIndustry", '("through-glass via" OR "glass core substrate") (production OR qualification OR investment OR capacity OR customer)'),
    ("国外·IEEE", 'site:ieee.org ("through-glass via" OR "glass core substrate")'),
    ("国外·IMAPS", 'site:imaps.org ("through-glass via" OR "glass core substrate" OR "glass interposer")'),
    ("国外·ECTC", 'site:ectc.net ("through-glass via" OR "glass core substrate" OR "glass interposer")'),
    ("国外·TheElec", 'site:thelec.net ("glass substrate" OR "glass core substrate" OR TGV) semiconductor'),
    ("国外·SemiconductorEngineering", 'site:semiengineering.com ("glass substrate" OR "glass core substrate" OR "through-glass via")'),
]

STRONG_TERMS = [
    "through-glass via", "through glass via", "through glass vias", "glass core substrate",
    "glass-core substrate", "glass interposer", "玻璃通孔", "玻璃互连孔", "玻璃芯基板", "玻璃中介层"
]
TGV_CONTEXT = [
    "semiconductor", "packaging", "package", "substrate", "interposer", "wafer", "via",
    "半导体", "封装", "基板", "中介层", "晶圆", "通孔", "芯片"
]

def clean(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()

def parse_date(value):
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return ""

def is_tgv_relevant(text):
    t = (text or "").lower()
    if any(term in t for term in STRONG_TERMS):
        return True
    # 单独出现 TGV 时必须同时具备半导体/封装上下文，避免法国高速列车误报。
    return bool(re.search(r"\btgv\b", t)) and any(k in t for k in TGV_CONTEXT)

def classify(text):
    t=(text or "").lower()
    if any(k in t for k in ["laser drilling","etching","metallization","plating","fabrication","工艺","激光","蚀刻","金属化","电镀","填孔"]):
        return "工艺技术"
    if any(k in t for k in ["production","capacity","investment","qualification","customer","量产","产线","扩产","投资","客户验证"]):
        return "产业进展"
    if any(k in t for k in ["patent","research","paper","conference","论文","专利","研究"]):
        return "研发/论文"
    return "综合资讯"

def needs_translation(text):
    if not text: return False
    latin=len(re.findall(r"[A-Za-z]",text))
    cjk=len(re.findall(r"[\u4e00-\u9fff]",text))
    return latin >= 8 and latin > cjk * 1.5

def translate_zh(text):
    if not text or not needs_translation(text):
        return text
    try:
        q=urllib.parse.urlencode({"client":"gtx","sl":"auto","tl":"zh-CN","dt":"t","q":text[:1200]})
        req=urllib.request.Request(TRANSLATION_ENDPOINT+"?"+q,headers=HEADERS)
        with urllib.request.urlopen(req,timeout=4) as r:
            data=json.load(r)
        translated="".join(p[0] for p in data[0] if p and p[0]).strip()
        return translated if translated else text
    except Exception:
        return text

def fetch_google(group, query, source_type, chinese=False):
    edition="&hl=zh-CN&gl=CN&ceid=CN:zh-Hans" if chinese else "&hl=en-US&gl=US&ceid=US:en"
    url="https://news.google.com/rss/search?q="+urllib.parse.quote(query)+edition
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=12) as r:
        root=ET.fromstring(r.read())
    rows=[]
    for item in root.findall(".//item")[:60]:
        title=clean(item.findtext("title"))
        summary=clean(item.findtext("description"))
        link=(item.findtext("link") or "").strip()
        source=clean(item.findtext("source")) or group
        text=title+" "+summary
        if not title or not link or not is_tgv_relevant(text):
            continue
        rows.append({
            "source_group":group,
            "source_type":source_type,
            "source":source,
            "original_title":title,
            "original_summary":summary if summary != title else "",
            "date":parse_date(item.findtext("pubDate") or ""),
            "url":link,
        })
    return rows

def collect():
    jobs=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for g,q in DOMESTIC_QUERIES:
            jobs.append(pool.submit(fetch_google,g,q,"国内网站",True))
        for g,q in FOREIGN_QUERIES:
            jobs.append(pool.submit(fetch_google,g,q,"国外网站",False))
        rows=[]
        for f in as_completed(jobs):
            try:
                rows.extend(f.result())
            except Exception as exc:
                print("检索失败：",str(exc)[:120])
    return rows

def main():
    rows=collect()
    dedup={}
    for r in rows:
        key=(r["source_type"], re.sub(r"\W+","",r["original_title"].lower()))
        if key not in dedup:
            dedup[key]=r
    rows=list(dedup.values())

    # 仅翻译最新的国外标题，失败则直接保留原文，不阻塞采集。
    foreign=[r for r in rows if r["source_type"]=="国外网站"]
    foreign.sort(key=lambda x:x.get("date",""),reverse=True)
    translate_targets=set(id(x) for x in foreign[:80])

    news=[]
    for r in rows:
        raw_title=r["original_title"]
        raw_summary=r["original_summary"]
        title=translate_zh(raw_title) if id(r) in translate_targets else raw_title
        summary=raw_summary
        news.append({
            "title":title,
            "original_title":raw_title,
            "summary":summary,
            "original_summary":raw_summary,
            "date":r["date"],
            "source":r["source"],
            "source_group":r["source_group"],
            "source_type":r["source_type"],
            "category":classify(raw_title+" "+raw_summary),
            "url":r["url"],
            "translation_status":"已翻译标题" if title != raw_title else "原文",
            "topics":["TGV/玻璃基板"],
            "relevance_level":"核心相关",
        })

    news.sort(key=lambda x:x.get("date",""),reverse=True)
    # 只保留有日期且 90 天内的归档，页面再提供 3/7/30 天筛选。
    cutoff=datetime.now(timezone.utc).timestamp()-90*86400
    kept=[]
    for n in news:
        try:
            ts=datetime.strptime(n["date"],"%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
            if ts >= cutoff: kept.append(n)
        except Exception:
            pass

    tmp=DATA_FILE+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump({
            "updated_at":datetime.now(timezone.utc).isoformat(),
            "scope":"TGV / Through-Glass Via / Glass Core Substrate only",
            "news":kept[:1200]
        },f,ensure_ascii=False,indent=2)
    os.replace(tmp,DATA_FILE)
    cn=sum(1 for n in kept if n["source_type"]=="国内网站")
    foreign_n=sum(1 for n in kept if n["source_type"]=="国外网站")
    print(f"完成：共 {len(kept)} 条；国内网站 {cn} 条；国外网站 {foreign_n} 条。")

if __name__=="__main__":
    main()
