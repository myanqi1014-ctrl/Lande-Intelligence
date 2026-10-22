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
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(ROOT, "news.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TGVIntelligence/1.1)"}
TRANSLATION_ENDPOINT = "https://translate.googleapis.com/translate_a/single"

# Open discovery, not a fixed publisher whitelist:
# Google News RSS is used as a no-key public search index. Site-specific queries are supplementary.
QUERIES = [
    ("TGV·英文", '("through-glass via" OR "glass core substrate" OR "glass interposer" OR "TGV technology")'),
    ("TGV·中文", '(TGV OR 玻璃通孔 OR 玻璃芯基板 OR 玻璃中介层)'),
    ("玻璃基板·产业", '("glass substrate" OR "glass core substrate" OR 玻璃基板 OR 玻璃芯基板) (Intel OR AMD OR NVIDIA OR packaging OR 封装 OR substrate OR interposer)'),
    ("CPO·核心", '("co-packaged optics" OR CPO) (AI OR datacenter OR optical OR silicon photonics)'),
    ("NPO·LPO", '("near-packaged optics" OR NPO OR "linear pluggable optics" OR LPO OR LRO) (AI OR optical OR datacenter)'),
    ("光互联·AI", '("optical interconnect" OR "optical I/O" OR "optical IO") (AI OR GPU OR accelerator OR scale-up OR scale-out)'),
    ("硅光·光引擎", '("silicon photonics" OR SiPh OR "optical engine" OR PIC) (CPO OR NPO OR AI OR datacenter)'),
    ("光芯片·激光器", '(InP OR "CW laser" OR DFB OR EML OR VCSEL OR modulator OR TFLN) (CPO OR NPO OR optical interconnect OR AI)'),
    ("高速光模块", '("800G" OR "1.6T" OR "3.2T" OR "400G/lane" OR "200G/lane") (optical module OR transceiver OR 光模块 OR 光互联)'),
    ("Scale-up·Scale-out", '("scale-up" OR "scale-out") ("optical interconnect" OR CPO OR NPO OR "optical I/O")'),
    ("OCS·光交换", '("optical circuit switch" OR OCS OR "all-optical switching") (AI OR datacenter OR scale-up OR scale-out)'),
    ("玻璃×CPO", '("glass substrate" OR "glass interposer" OR "glass waveguide" OR TGV) ("co-packaged optics" OR CPO)'),
    ("MicroLED光互联", '("Micro-LED" OR microLED) ("optical interconnect" OR optical communication OR CPO)'),
    ("微信公众号·TGV玻璃", 'site:mp.weixin.qq.com (TGV OR 玻璃通孔 OR 玻璃基板 OR 玻璃芯基板)'),
    ("微信公众号·CPO光互联", 'site:mp.weixin.qq.com (CPO OR NPO OR LPO OR 光互联 OR 硅光 OR 光引擎) (AI OR 算力 OR 数据中心 OR 光模块)'),
    ("微信公众号·光芯片", 'site:mp.weixin.qq.com (InP OR CW激光器 OR DFB OR EML OR TFLN OR 硅光) (CPO OR 光互联 OR 光模块)'),
    ("台湾科技媒体", '(TGV OR 玻璃基板 OR CPO OR NPO OR LPO OR 矽光 OR 光互連) 台灣 科技'),
    ("韩国科技媒体", '(TGV OR "glass substrate" OR CPO OR NPO OR "silicon photonics") Korea semiconductor'),
    ("日本科技媒体", '(TGV OR "glass substrate" OR CPO OR NPO OR "silicon photonics") Japan semiconductor'),
    ("TheElec", 'site:thelec.kr (TGV OR "glass substrate" OR CPO OR NPO OR "silicon photonics")'),
    ("Xenospectrum", 'site:xenospectrum.com (TGV OR "glass substrate" OR CPO OR NPO OR "optical interconnect")'),
    ("ETNews", 'site:en.etnews.com (TGV OR "glass substrate" OR CPO OR NPO OR "silicon photonics")'),
    ("BigGo Finance", 'site:finance.biggo.com (TGV OR 玻璃基板 OR CPO OR NPO OR 矽光 OR 光互連)'),
    ("Seoul Economic Daily", 'site:en.sedaily.com (TGV OR "glass substrate" OR CPO OR NPO OR "silicon photonics")'),
    ("论文·专利", '("through-glass via" OR "glass core substrate" OR CPO OR NPO OR "optical I/O" OR "silicon photonics") (research OR patent OR conference OR paper)'),
    ("arXiv·光互联预印本", 'site:arxiv.org (CPO OR "co-packaged optics" OR NPO OR "optical interconnect" OR "optical I/O" OR "silicon photonics")'),
    ("arXiv·玻璃TGV预印本", 'site:arxiv.org ("through-glass via" OR "glass core substrate" OR "glass interposer")'),
    ("TechRxiv·预印本", 'site:techrxiv.org (CPO OR NPO OR "optical interconnect" OR "silicon photonics" OR TGV OR "glass substrate")'),
    ("Optica Open·预印本", 'site:opg.optica.org ("Optica Open" OR preprint) (CPO OR "optical interconnect" OR "silicon photonics" OR "optical engine" OR TGV)'),
    ("Research Square·预印本", 'site:researchsquare.com (CPO OR "optical interconnect" OR "silicon photonics" OR photonics OR TGV)'),
    ("官方·NVIDIA", 'site:nvidia.com (CPO OR "co-packaged optics" OR "silicon photonics" OR "optical networking" OR "optical interconnect")'),
    ("官方·Broadcom", 'site:broadcom.com (CPO OR "co-packaged optics" OR "silicon photonics" OR "optical engine" OR LPO)'),
    ("官方·Intel", 'site:intel.com ("glass substrate" OR "glass core substrate" OR "silicon photonics" OR "optical I/O" OR CPO)'),
    ("官方·TSMC", 'site:tsmc.com (silicon photonics OR CPO OR COUPE OR photonics OR optical)'),
    ("官方·Marvell", 'site:marvell.com (CPO OR "silicon photonics" OR "optical interconnect" OR "optical DSP" OR 1.6T)'),
    ("官方·Coherent", 'site:coherent.com (CPO OR "optical engine" OR "silicon photonics" OR 1.6T OR "CW laser")'),
    ("官方·Lumentum", 'site:lumentum.com (CPO OR "CW laser" OR "optical interconnect" OR 1.6T OR photonics)'),
    ("官方·Cisco", 'site:cisco.com (CPO OR "silicon photonics" OR "optical interconnect" OR "co-packaged optics")'),
    ("会议·OFC", 'site:ofcconference.org (CPO OR NPO OR "optical interconnect" OR "silicon photonics" OR "optical I/O" OR TGV)'),
    ("会议·ECOC", '(site:ecoc2026.org OR site:ecoc.org) (CPO OR NPO OR "optical interconnect" OR "silicon photonics" OR 1.6T)'),
    ("会议·ECTC", 'site:ectc.net (TGV OR "glass substrate" OR "glass core substrate" OR photonics OR "optical interconnect")'),
    ("会议·SPIE", 'site:spie.org (CPO OR "optical interconnect" OR "silicon photonics" OR "optical I/O" OR TGV)'),
    ("机构·Optica", 'site:optica.org (CPO OR NPO OR "optical interconnect" OR "silicon photonics" OR "optical I/O")'),
    ("机构·IEEE", 'site:ieee.org (CPO OR "co-packaged optics" OR "glass core substrate" OR TGV OR "optical interconnect")'),
    ("全球英文·CPO", '"co-packaged optics" AI datacenter silicon photonics'),
    ("全球英文·NPO_LPO", '("near-packaged optics" OR "linear pluggable optics") AI datacenter'),
    ("全球英文·OpticalIO", '("optical I/O" OR "optical interconnect") AI GPU accelerator'),
    ("全球英文·SiliconPhotonics", '"silicon photonics" AI datacenter optical engine'),
    ("全球英文·OpticalEngine", '"optical engine" CPO AI datacenter'),
    ("全球英文·Transceiver", '("800G" OR "1.6T" OR "3.2T") optical transceiver datacenter'),
    ("全球英文·InP_Laser", '(InP OR "CW laser" OR DFB OR EML) optical interconnect CPO'),
    ("全球英文·TFLN", '("thin film lithium niobate" OR TFLN) modulator optical interconnect'),
    ("全球英文·OCS", '"optical circuit switch" AI datacenter'),
    ("全球英文·GlassCore", '("glass core substrate" OR "glass interposer" OR "through-glass via") semiconductor packaging'),
    ("全球英文·MicroLED", 'MicroLED optical interconnect optical communication')
]

# Dedicated public-web discovery for Chinese/WeChat content. Google News alone misses most public-account pages.
WEB_QUERIES = [
    ("微信公众号·CPO", 'site:mp.weixin.qq.com CPO 共封装光学'),
    ("微信公众号·NPO_LPO", 'site:mp.weixin.qq.com NPO LPO 光模块'),
    ("微信公众号·硅光", 'site:mp.weixin.qq.com 硅光 硅光子 光引擎'),
    ("微信公众号·光互联", 'site:mp.weixin.qq.com 光互联 光互连 AI 算力'),
    ("微信公众号·高速光模块", 'site:mp.weixin.qq.com 800G 1.6T 光模块'),
    ("微信公众号·光芯片", 'site:mp.weixin.qq.com 磷化铟 InP DFB EML CW激光器'),
    ("微信公众号·TFLN", 'site:mp.weixin.qq.com TFLN 薄膜铌酸锂 调制器'),
    ("微信公众号·TGV", 'site:mp.weixin.qq.com TGV 玻璃通孔 玻璃基板 玻璃芯基板'),
    ("微信公众号·OCS", 'site:mp.weixin.qq.com OCS 光交换 全光交换'),
    ("微信公众号·OpticalIO", 'site:mp.weixin.qq.com Optical I/O 光互联'),
    ("微信公众号·MicroLED", 'site:mp.weixin.qq.com MicroLED 光互联 光通信'),
]


# Priority WeChat/public-account watchlist. These are searched by account name + topic terms
# through public web indexing. This improves precision but still cannot equal WeChat Search coverage.
WECHAT_ACCOUNTS = [
    # 行业媒体 / 产业资讯
    "讯石光通讯",
    "ICC讯石",
    "光通信女人",
    "C114通信网",
    "光电汇OESHOW",
    "中国电子报",
    "半导体行业观察",
    "芯智讯",
    "全球半导体观察",
    "TrendForce集邦咨询",
    "LEDinside",
    "电子工程专辑",
    "爱集微",
    "芯东西",
    "光纤在线",

    # 券商 / 产业研究
    "国盛通信",
    "中信建投通信",
    "天风通信",
    "华西通信",
    "申万通信",

    # 企业官方
    "中际旭创",
    "新易盛",
    "光迅科技",
    "华工科技",
    "天孚通信",
    "源杰科技",
    "长光华芯",
    "仕佳光子",
    "光库科技",
    "博创科技",
]

WECHAT_TOPIC_TERMS = [
    "CPO 共封装光学",
    "NPO LPO",
    "硅光 硅光子 光引擎",
    "光互联 光互连 Optical I/O",
    "800G 1.6T 3.2T 光模块",
    "InP 磷化铟 CW激光器 DFB EML",
    "TFLN 薄膜铌酸锂",
    "TGV 玻璃通孔 玻璃基板 玻璃芯基板",
    "OCS 光交换",
    "MicroLED 光互联",
]

ARXIV_QUERIES = [
    ("arXiv·CPO光互联", 'all:"co-packaged optics" OR all:"optical interconnect" OR all:"optical I/O"'),
    ("arXiv·硅光光引擎", 'all:"silicon photonics" OR all:"optical engine"'),
    ("arXiv·高速光模块", 'all:"1.6T" OR all:"800G" OR all:"optical transceiver"'),
    ("arXiv·玻璃TGV", 'all:"through-glass via" OR all:"glass core substrate" OR all:"glass interposer"'),
    ("arXiv·光芯片器件", 'all:"thin film lithium niobate" OR all:"CW laser" OR all:"InP laser"'),
]

TOPIC_TERMS = {
    "TGV/玻璃基板": ["through-glass via","through glass via","glass via","tgv technology","tgv process","玻璃通孔","玻璃芯基板","glass core substrate","glass interposer","玻璃中介层"],
    "CPO/NPO/LPO": ["co-packaged optics","cpo","near-packaged optics","npo","linear pluggable optics","lpo","lro","obo","xpo"],
    "AI光互联": ["optical interconnect","optical i/o","optical io","光互联","光互連","scale-up","scale-out","gpu interconnect"],
    "硅光/光引擎": ["silicon photonics","silicon photonic","siph","optical engine","photonic integrated circuit","pic","硅光","矽光","光引擎"],
    "光芯片/器件": ["inp","cw laser","dfb","eml","vcsel","tfln","thin-film lithium niobate","modulator","光芯片","激光器","調制器","调制器"],
    "高速光模块": ["800g","1.6t","3.2t","400g/lane","200g/lane","optical transceiver","optical module","光模块"],
    "OCS/光交换": ["optical circuit switch","all-optical switching","ocs","光交换","全光交换"],
    "MicroLED光互联": ["micro-led","microled"],
}
CONTEXT_TERMS = ["ai","artificial intelligence","datacenter","data center","gpu","accelerator","switch","ethernet","scale-up","scale-out","optical","photon","光","算力","数据中心","交換機","交换机","半导体","semiconductor","packaging","封装"]

def topic_for(text):
    t = text.lower()
    hits = []
    for topic, terms in TOPIC_TERMS.items():
        if any(term in t for term in terms):
            hits.append(topic)
    # Avoid generic acronym collisions: weak device terms require optical/AI context.
    if hits and ("光芯片/器件" not in hits or any(k in t for k in CONTEXT_TERMS)):
        return hits
    return []

def relevance_level(text):
    topics = topic_for(text)
    if not topics:
        return None
    t = text.lower()
    strong = any(k in t for k in ["through-glass via","glass core substrate","co-packaged optics","near-packaged optics","optical interconnect","optical i/o","silicon photonics","玻璃通孔","玻璃芯基板","光互联","硅光"])
    return "核心相关" if strong else "产业链相关"

def is_relevant(text):
    return relevance_level(text) is not None

def classify_content(text):
    """Classify AI high-speed optical-interconnect articles by evidence type."""
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
        "quality_reason": "标题/摘要与监测主题相关，但暂未识别到明确技术指标或产业化里程碑",
        "quality_score": 45,
    }


def clean(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()

def needs_zh_translation(text):
    """Return True when visible text still looks predominantly non-Chinese."""
    if not text:
        return False
    latin = len(re.findall(r"[A-Za-z]", text))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    # English/Korean-source headlines frequently contain mostly Latin text.
    return latin >= 8 and latin > cjk * 1.5

def translation_is_valid(source, translated):
    if not translated:
        return False
    if needs_zh_translation(source) and needs_zh_translation(translated):
        return False
    return translated.strip() != ""

def translate_zh(text, cache):
    if not text:
        return ""
    cached = cache.get(text)
    if cached and translation_is_valid(text, cached):
        return cached
    params = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": text})
    request = urllib.request.Request(TRANSLATION_ENDPOINT + "?" + params, headers=HEADERS)
    last_error = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.load(response)
            translated = "".join(part[0] for part in data[0] if part and part[0]).strip()
            if translation_is_valid(text, translated):
                cache[text] = translated
                time.sleep(0.08)
                return translated
            last_error = "返回内容仍未翻译"
        except Exception as exc:
            last_error = str(exc)[:100]
        time.sleep(0.6 * (attempt + 1))
    print(f"翻译失败，暂保留原文（下次会重试）：{last_error}")
    return text

def translate_many(texts, cache, workers=3):
    """Translate unique strings concurrently to reduce workflow runtime while keeping all display text in zh-CN."""
    pending = [t for t in dict.fromkeys(texts) if t and t not in cache]
    if not pending:
        return
    def one(text):
        local = {}
        return text, translate_zh(text, local)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, t) for t in pending]
        for fut in as_completed(futures):
            try:
                src, dst = fut.result()
                cache[src] = dst
            except Exception:
                pass


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
    # Use an English Google News index for English/global queries so overseas sources are not suppressed
    # by the Traditional-Chinese/Taiwan edition. Chinese/WeChat queries retain the Chinese edition.
    # Route by source intent, not by whether the query happens to contain Chinese terms.
    # Mixed technical queries should default to the global English index so overseas coverage is not suppressed.
    chinese_groups = ("TGV·中文", "微信公众号", "台湾科技媒体", "BigGo Finance")
    chinese_query = query_group.startswith(chinese_groups)
    edition = "&hl=zh-CN&gl=TW&ceid=TW:zh-Hant" if chinese_query else "&hl=en-US&gl=US&ceid=US:en"
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + edition
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
            "source_type": ("预印本" if any(k in query_group for k in ("arXiv", "TechRxiv", "Optica Open", "Research Square")) else ("企业官方" if query_group.startswith("官方·") else ("会议/机构" if query_group.startswith(("会议·", "机构·")) else "产业资讯"))),
            "url": link,
        })
    return rows


def fetch_bing_web(query_group, query):
    """Public Bing HTML discovery, mainly to recover indexed WeChat/public-web pages missed by Google News."""
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "count": 50, "setlang": "zh-Hans"})
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        page = response.read().decode("utf-8", "ignore")
    rows = []
    # Bing result blocks: extract outbound href + visible title. Keep only public WeChat pages for these queries.
    for m in re.finditer(r'<li class="b_algo".*?<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.I | re.S):
        link = html.unescape(m.group(1))
        title = clean(m.group(2))
        if "mp.weixin.qq.com" not in link or not title:
            continue
        text = title
        level = relevance_level(text)
        if not level:
            # The query itself is tightly scoped; allow titles carrying at least one monitored technical term.
            level = "产业链相关" if topic_for(query + " " + title) else None
        if not level:
            continue
        rows.append({
            "relevance_level": level, "source_group": query_group,
            "original_title": title, "original_summary": "",
            "date": "", "source": "微信公众号", "source_type": "微信/公开内容", "url": link,
        })
    return rows[:30]


def fetch_wechat_accounts():
    """Targeted public-web discovery for priority WeChat accounts."""
    rows = []
    seen = set()
    for account in WECHAT_ACCOUNTS:
        # One combined query per account keeps runtime reasonable while preserving targeted discovery.
        query = f'site:mp.weixin.qq.com "{account}" (CPO OR NPO OR LPO OR 硅光 OR 光互联 OR 光互连 OR 光模块 OR 800G OR 1.6T OR TGV OR 玻璃基板 OR OCS OR TFLN OR MicroLED)'
        try:
            found = fetch_bing_web("重点公众号·" + account, query)
            for row in found:
                if row["url"] in seen:
                    continue
                seen.add(row["url"])
                row["source"] = account
                row["source_type"] = "微信/重点公众号"
                rows.append(row)
        except Exception as exc:
            print(f"重点公众号检索失败 [{account}]: {str(exc)[:120]}")
    return rows


def fetch_arxiv(query_group, query):
    """Direct arXiv API ingestion; independent of Google News indexing."""
    params = urllib.parse.urlencode({
        "search_query": query, "start": 0, "max_results": 30,
        "sortBy": "submittedDate", "sortOrder": "descending"
    })
    request = urllib.request.Request("https://export.arxiv.org/api/query?" + params, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())
    ns = {"a": "http://www.w3.org/2005/Atom"}
    rows = []
    for entry in root.findall("a:entry", ns):
        title = clean(entry.findtext("a:title", default="", namespaces=ns))
        summary = clean(entry.findtext("a:summary", default="", namespaces=ns))
        link = entry.findtext("a:id", default="", namespaces=ns).strip()
        published = entry.findtext("a:published", default="", namespaces=ns)
        if not title or not link:
            continue
        text = title + " " + summary
        level = relevance_level(text)
        if not level:
            continue
        rows.append({
            "relevance_level": level, "source_group": query_group,
            "original_title": title, "original_summary": summary,
            "date": published[:10], "source": "arXiv", "source_type": "预印本", "url": link,
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

    web_successes = 0
    for group, query in WEB_QUERIES:
        try:
            rows = fetch_bing_web(group, query)
            web_successes += 1
            for row in rows:
                if row["url"] not in seen:
                    seen.add(row["url"]); found.append(row)
            print(f"{group} [公开网页]: {len(rows)} 条相关结果")
        except Exception as exc:
            print(f"公开网页检索失败 [{group}]: {str(exc)[:160]}")

    wechat_account_rows = fetch_wechat_accounts()
    wechat_account_successes = len(WECHAT_ACCOUNTS)
    for row in wechat_account_rows:
        if row["url"] not in seen:
            seen.add(row["url"])
            found.append(row)
    print(f"重点公众号白名单：发现 {len(wechat_account_rows)} 条公开索引结果")

    arxiv_successes = 0
    for group, query in ARXIV_QUERIES:
        try:
            rows = fetch_arxiv(group, query)
            arxiv_successes += 1
            for row in rows:
                if row["url"] not in seen:
                    seen.add(row["url"]); found.append(row)
            print(f"{group} [arXiv直连]: {len(rows)} 条相关结果")
        except Exception as exc:
            print(f"arXiv检索失败 [{group}]: {str(exc)[:160]}")

    if not found:
        print("本次没有获取到相关新闻；保留现有数据。")
        return

    # Reuse translations from the existing archive even when the same article is rediscovered
    # through a different aggregator URL. This avoids hundreds of repeated translation requests.
    cache = {}
    for item in previous:
        if not isinstance(item, dict):
            continue
        ot, tt = item.get("original_title"), item.get("title")
        osum, tsum = item.get("original_summary"), item.get("summary")
        if ot and tt and translation_is_valid(ot, tt):
            cache[ot] = tt
        if osum and tsum and tsum != "聚合源未提供可靠摘要，请打开原文核实。" and translation_is_valid(osum, tsum):
            cache[osum] = tsum
    # Translate every visible title and summary to Simplified Chinese in parallel.
    to_translate = []
    for row in found:
        to_translate.append(row.get("original_title", ""))
        if row.get("original_summary"):
            to_translate.append(row["original_summary"][:900])
    translate_many(to_translate, cache, workers=3)

    news = []
    for row in found:
        old = old_by_url.get(row["url"], {})
        source_title = row["original_title"]
        source_summary = row["original_summary"]
        title = cache.get(source_title) or translate_zh(source_title, cache)
        summary = cache.get(source_summary[:900]) if source_summary else None
        if not summary:
            summary = translate_zh(source_summary[:900], cache) if source_summary else "聚合源未提供可靠摘要，请打开原文核实。"
        quality = classify_content(source_title + " " + source_summary)
        news.append({
            "title": title,
            "original_title": title,
            "source_original_title": source_title,
            "summary": summary,
            "original_summary": summary,
            "source_original_summary": source_summary,
            "date": row["date"],
            "source": row["source"],
            "source_group": row["source_group"],
            "source_type": row.get("source_type", "产业资讯"),
            "category": category_for(source_title + " " + source_summary),
            "url": row["url"],
            "translation_status": ("已翻译为简体中文；原始语言文本后台保留" if not needs_zh_translation(title) else "翻译暂未成功，下次自动重试"),
            "relevance": row["relevance_level"] + "：关键词规则初筛通过，仍需人工核验",
            "relevance_level": row["relevance_level"],
            "topics": topic_for(source_title + " " + source_summary),
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
            old["topics"] = topic_for(searchable)
            if not old.get("source_type"):
                old["source_type"] = "预印本" if any(k in str(old.get("source_group", "")) for k in ("arXiv", "TechRxiv", "Optica Open", "Research Square")) else "产业资讯"
            old["relevance"] = level + "：历史记录通过关键词规则初筛，仍需人工核验"
            quality = classify_content(searchable)
            old["content_type"] = quality["content_type"]
            old["quality_reason"] = quality["quality_reason"]
            old["quality_score"] = quality["quality_score"]
            news.append(old)
            known.add(old["url"])
    news.sort(key=lambda n: n.get("date", ""), reverse=True)
    news = news[:2000]
    temp = DATA_FILE + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source_queries_succeeded": successes + web_successes + wechat_account_successes + arxiv_successes,
            "source_queries_total": len(QUERIES) + len(WEB_QUERIES) + len(WECHAT_ACCOUNTS) + len(ARXIV_QUERIES),
            "search_method": "AI high-speed optical interconnect monitoring: TGV/glass substrates, CPO/NPO/LPO, silicon photonics, optical engines, optical chips/devices, high-speed transceivers, scale-up/scale-out optical I/O, OCS and MicroLED optical interconnect; Multi-channel discovery: expanded global-English and Chinese Google News queries, dedicated public-web discovery for indexed WeChat pages, direct arXiv API, plus official company and conference/institution discovery. All visible titles and summaries are normalized to Simplified Chinese while raw source-language text is retained separately.",
            "news": news
        }, f, ensure_ascii=False, indent=2)
    os.replace(temp, DATA_FILE)
    direct_count = sum(1 for n in news if n.get("relevance_level") == "核心相关")
    related_count = sum(1 for n in news if n.get("relevance_level") == "产业链相关")
    types = {name: sum(1 for n in news if n.get("content_type") == name) for name in ("技术进展", "产业化进展", "市场观察", "待核验")}
    print(f"完成：Google News {successes}/{len(QUERIES)}；公开网页 {web_successes}/{len(WEB_QUERIES)}；重点公众号 {len(wechat_account_rows)} 条；arXiv {arxiv_successes}/{len(ARXIV_QUERIES)}；归档 {len(news)} 条；核心相关 {direct_count} 条，产业链相关 {related_count} 条。")
    print("内容质量分类：" + "；".join(f"{k} {v} 条" for k, v in types.items()))
    print("说明：微信公众号仅能发现被公开索引的文章；未被索引、需登录或受限制的文章不会保证采集到。")

if __name__ == "__main__":
    main()
