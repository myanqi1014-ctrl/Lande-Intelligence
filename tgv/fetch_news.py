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
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TGVTechIntel/3.0)"}
TRANSLATION_ENDPOINT = "https://translate.googleapis.com/translate_a/single"

# 监测范围：TGV + AI 高速光互联全链路。全部通过公开网站/Google News RSS发现，
# 不依赖微信公众号，不直接硬爬高反爬站点。
DOMESTIC_QUERIES = [
    # 泛主题发现：拆细关键词，减少超长布尔查询漏检
    ("国内·TGV基础", 'TGV 玻璃通孔 半导体'),
    ("国内·玻璃芯基板", '玻璃芯基板 先进封装'),
    ("国内·玻璃中介层", '玻璃中介层 半导体'),
    ("国内·玻璃基板封装", '玻璃基板 先进封装 半导体'),
    ("国内·CPO基础", 'CPO 光通信'),
    ("国内·共封装光学", '共封装光学 数据中心'),
    ("国内·NPO", 'NPO 光通信'),
    ("国内·LPO", 'LPO 光模块'),
    ("国内·AI光互联基础", 'AI 光互联 数据中心'),
    ("国内·OpticalIO", 'Optical I/O AI 光互联'),
    ("国内·硅光基础", '硅光 数据中心'),
    ("国内·硅光子", '硅光子 CPO'),
    ("国内·光引擎基础", '光引擎 CPO'),
    ("国内·800G", '800G 光模块'),
    ("国内·1.6T", '1.6T 光模块'),
    ("国内·3.2T", '3.2T 光模块'),
    ("国内·InP", '磷化铟 光通信 芯片'),
    ("国内·DFB_EML", 'DFB EML 光通信'),
    ("国内·TFLN基础", '薄膜铌酸锂 光通信'),
    ("国内·OCS基础", 'OCS 光交换 数据中心'),
    ("国内·MicroLED光互联基础", 'MicroLED 光互联'),
    ("国内·ScaleUp基础", 'Scale-up 光互联 AI'),
    # 原有泛主题发现
    ("国内·TGV", '(TGV OR 玻璃通孔 OR 玻璃芯基板 OR 玻璃中介层) 半导体 封装'),
    ("国内·玻璃基板", '("玻璃基板" OR "玻璃芯基板" OR "玻璃中介层") (半导体 OR 先进封装)'),
    ("国内·CPO", '(CPO OR 共封装光学 OR 共封装光器件) (AI OR 算力 OR 数据中心 OR 光通信)'),
    ("国内·NPO_LPO", '(NPO OR LPO OR LRO OR 近封装光学 OR 线性可插拔) 光通信'),
    ("国内·AI光互联", '("AI光互联" OR "光互联" OR "光互连" OR Optical I/O) (算力 OR GPU OR 数据中心)'),
    ("国内·硅光", '(硅光 OR 硅光子 OR Silicon Photonics) (AI OR 光通信 OR 数据中心 OR CPO)'),
    ("国内·光引擎", '("光引擎" OR Optical Engine) (CPO OR 硅光 OR AI OR 光模块)'),
    ("国内·高速光模块", '(800G OR 1.6T OR 3.2T OR 200G/lane OR 400G/lane) (光模块 OR 光通信)'),
    ("国内·光芯片", '(InP OR 磷化铟 OR DFB OR EML OR CW激光器 OR VCSEL OR TFLN OR 薄膜铌酸锂) 光通信'),
    ("国内·OCS", '(OCS OR 光路交换 OR 光电路交换 OR 全光交换) (AI OR 数据中心 OR 算力)'),
    ("国内·MicroLED光互联", '(MicroLED OR Micro-LED) (光互联 OR 光通信 OR 光互连)'),
    ("国内·ScaleUp", '(Scale-up OR Scale-out OR GPU互联) (光互联 OR CPO OR Optical I/O)'),

    # 国内产业/科技/财经公开网站
    ("国内·半导体行业观察", 'site:semiinsights.com (TGV OR CPO OR 硅光 OR 光互联 OR 光模块 OR 玻璃基板)'),
    ("国内·集邦咨询", 'site:trendforce.cn (TGV OR CPO OR 硅光 OR 光互联 OR 1.6T OR 光模块 OR 玻璃基板)'),
    ("国内·DIGITIMES中文", 'site:digitimes.com.tw OR site:digitimes.com (CPO OR 硅光 OR 光互联 OR 光模块 OR 玻璃基板)'),
    ("国内·爱集微", 'site:ijiwei.com (TGV OR CPO OR 硅光 OR 光互联 OR 1.6T OR 光模块 OR OCS)'),
    ("国内·电子工程专辑", 'site:eet-china.com (TGV OR CPO OR 硅光 OR 光互联 OR 1.6T OR 光模块)'),
    ("国内·OFweek", 'site:ofweek.com (TGV OR CPO OR 硅光 OR 光互联 OR 1.6T OR 光模块)'),
    ("国内·C114", 'site:c114.com.cn (CPO OR 硅光 OR 光互联 OR 800G OR 1.6T OR 光模块)'),
    ("国内·通信世界", 'site:cww.net.cn (CPO OR 硅光 OR 光互联 OR 800G OR 1.6T OR 光模块)'),
    ("国内·通信产业网", 'site:ccidcom.com (CPO OR 硅光 OR 光互联 OR 800G OR 1.6T)'),
    ("国内·芯智讯", 'site:icsmart.cn (TGV OR CPO OR 硅光 OR 光互联 OR 光模块)'),
    ("国内·未来半导体", 'site:fsemi.tech (TGV OR 玻璃基板 OR CPO OR 硅光 OR 光互联)'),
    ("国内·半导体产业纵横", 'site:icviews.cn (TGV OR CPO OR 硅光 OR 光互联 OR 光模块)'),
    ("国内·电子发烧友", 'site:elecfans.com (TGV OR CPO OR 硅光 OR 光互联 OR 1.6T OR 光模块)'),
    ("国内·与非网", 'site:eefocus.com (TGV OR CPO OR 硅光 OR 光互联 OR 1.6T OR 光模块)'),
    ("国内·21ic", 'site:21ic.com (TGV OR CPO OR 硅光 OR 光互联 OR 光模块)'),
    ("国内·EEWorld", 'site:eeworld.com.cn (TGV OR CPO OR 硅光 OR 光互联 OR 光模块)'),
    ("国内·中国电子报", 'site:ce.cn OR site:cenews.com.cn (TGV OR CPO OR 硅光 OR 光互联 OR 光模块)'),
    ("国内·证券时报", 'site:stcn.com (TGV OR CPO OR 硅光 OR 光互联 OR 1.6T OR 光模块)'),
    ("国内·中国证券网", 'site:cnstock.com (TGV OR CPO OR 硅光 OR 光互联 OR 1.6T OR 光模块)'),
    ("国内·财联社", 'site:cls.cn (TGV OR CPO OR 硅光 OR 光互联 OR 1.6T OR 光模块)'),
    ("国内·新浪财经", 'site:finance.sina.com.cn (TGV OR CPO OR 硅光 OR 光互联 OR 1.6T OR 光模块)'),
    ("国内·界面新闻", 'site:jiemian.com (CPO OR 硅光 OR 光互联 OR 光模块 OR 玻璃基板)'),
    ("国内·第一财经", 'site:yicai.com (CPO OR 硅光 OR 光互联 OR 光模块 OR 玻璃基板)'),
    ("国内·36氪", 'site:36kr.com (CPO OR 硅光 OR 光互联 OR 光模块 OR 玻璃基板)'),
    ("国内·钛媒体", 'site:tmtpost.com (CPO OR 硅光 OR 光互联 OR 光模块 OR 玻璃基板)'),
    ("国内·搜狐科技", 'site:sohu.com (CPO OR 硅光 OR 光互联 OR 1.6T OR 光模块 OR TGV)'),
    ("国内·网易科技", 'site:163.com (CPO OR 硅光 OR 光互联 OR 1.6T OR 光模块 OR TGV)'),
]

FOREIGN_QUERIES = [
    # 泛主题发现：增加短查询，提升近7天命中率
    ("国外·TGVBasic", '"through glass via" semiconductor'),
    ("国外·GlassCoreBasic", '"glass core substrate" packaging'),
    ("国外·GlassInterposerBasic", '"glass interposer" semiconductor'),
    ("国外·CPOBasic", '"co-packaged optics"'),
    ("国外·NPOBasic", '"near-packaged optics"'),
    ("国外·LPOBasic", '"linear pluggable optics"'),
    ("国外·OpticalInterconnectBasic", '"optical interconnect" AI'),
    ("国外·OpticalIOBasic", '"optical I/O" AI'),
    ("国外·SiliconPhotonicsBasic", '"silicon photonics" datacenter'),
    ("国外·OpticalEngineBasic", '"optical engine" photonics'),
    ("国外·800GBasic", '"800G" optical transceiver'),
    ("国外·1.6TBasic", '"1.6T" optical transceiver'),
    ("国外·3.2TBasic", '"3.2T" optical transceiver'),
    ("国外·InPBasic", 'InP laser optical communications'),
    ("国外·CWBasic", '"CW laser" CPO'),
    ("国外·TFLNBasic", '"thin film lithium niobate" modulator'),
    ("国外·OCSBasic", '"optical circuit switch" AI'),
    ("国外·MicroLEDBasic", 'MicroLED optical interconnect'),
    ("国外·ScaleUpBasic", '"scale-up" optical interconnect'),
    # 原有泛主题发现
    ("国外·TGV", '("through-glass via" OR "glass core substrate" OR "glass interposer") semiconductor packaging'),
    ("国外·CPO", '("co-packaged optics" OR CPO) (AI OR datacenter OR networking OR silicon photonics)'),
    ("国外·NPO_LPO", '("near-packaged optics" OR "linear pluggable optics" OR NPO OR LPO) datacenter optical'),
    ("国外·OpticalIO", '("optical I/O" OR "optical interconnect") (AI OR GPU OR accelerator OR scale-up OR scale-out)'),
    ("国外·SiliconPhotonics", '"silicon photonics" (AI OR datacenter OR CPO OR optical engine)'),
    ("国外·OpticalEngine", '"optical engine" (CPO OR silicon photonics OR AI datacenter)'),
    ("国外·Transceiver", '("800G" OR "1.6T" OR "3.2T") (optical transceiver OR optical module) datacenter'),
    ("国外·OpticalChip", '(InP OR "CW laser" OR DFB OR EML OR VCSEL OR TFLN OR "thin film lithium niobate") optical interconnect'),
    ("国外·OCS", '("optical circuit switch" OR OCS OR "all-optical switching") AI datacenter'),
    ("国外·MicroLED", '(MicroLED OR "Micro-LED") ("optical interconnect" OR "optical communication")'),

    # 海外产业媒体
    ("国外·DigiTimes", 'site:digitimes.com (TGV OR "glass substrate" OR "glass core substrate" OR CPO OR "silicon photonics" OR "optical interconnect" OR "optical I/O" OR 1.6T)'),
    ("国外·EE Times", 'site:eetimes.com (CPO OR "silicon photonics" OR "optical interconnect" OR "optical I/O" OR "glass substrate" OR 1.6T)'),
    ("国外·SemiconductorEngineering", 'site:semiengineering.com (CPO OR "silicon photonics" OR "optical interconnect" OR "glass substrate" OR "glass core substrate" OR photonics)'),
    ("国外·TechInsights", 'site:techinsights.com (CPO OR "co-packaged optics" OR "silicon photonics" OR "optical interconnect" OR "glass substrate" OR photonics)'),
    ("国外·YoleGroup", 'site:yolegroup.com (CPO OR "silicon photonics" OR "optical interconnect" OR "optical transceiver" OR "advanced packaging" OR "glass substrate")'),
    ("国外·TrendForce", 'site:trendforce.com (CPO OR "silicon photonics" OR "optical transceiver" OR 1.6T OR "glass substrate" OR "advanced packaging")'),
    ("国外·Omdia", 'site:omdia.tech.informa.com (CPO OR "silicon photonics" OR "optical interconnect" OR "optical transceiver" OR datacenter photonics)'),
    ("国外·LightCounting", 'site:lightcounting.com (CPO OR "silicon photonics" OR "optical interconnect" OR 1.6T OR "optical transceiver")'),
    ("国外·SemiAnalysis", 'site:semianalysis.com (CPO OR "optical interconnect" OR "silicon photonics" OR "scale-up" OR "scale-out" OR photonics)'),
    ("国外·SemiWiki", 'site:semiwiki.com (CPO OR "silicon photonics" OR "optical interconnect" OR "glass substrate" OR photonics)'),
    ("国外·SemiEngineeringPhotonics", 'site:semiengineering.com photonics (CPO OR silicon OR optical OR interconnect)'),
    ("国外·Lightwave", 'site:lightwaveonline.com (CPO OR silicon photonics OR optical interconnect OR 1.6T OR optical transceiver)'),
    ("国外·FibreSystems", 'site:fibre-systems.com (CPO OR silicon photonics OR optical interconnect OR 1.6T OR transceiver)'),
    ("国外·OpticsPhotonicsNews", 'site:optica-opn.org (CPO OR silicon photonics OR optical interconnect OR optical I/O)'),
    ("国外·PhotonicsSpectra", 'site:photonics.com (CPO OR silicon photonics OR optical interconnect OR optical engine OR TGV)'),
    ("国外·SemiconductorEngineering", 'site:semiengineering.com (CPO OR silicon photonics OR optical interconnect OR glass substrate OR glass core substrate)'),
    ("国外·EE Times", 'site:eetimes.com (CPO OR silicon photonics OR optical interconnect OR optical I/O OR glass substrate)'),
    ("国外·TheRegister", 'site:theregister.com (CPO OR optical interconnect OR silicon photonics OR optical networking)'),
    ("国外·Tomshardware", 'site:tomshardware.com (CPO OR silicon photonics OR optical interconnect OR glass substrate)'),
    ("国外·ServeTheHome", 'site:servethehome.com (CPO OR optical interconnect OR silicon photonics OR 1.6T)'),
    ("国外·DataCenterDynamics", 'site:datacenterdynamics.com (CPO OR optical interconnect OR silicon photonics OR optical networking)'),
    ("国外·BlocksAndFiles", 'site:blocksandfiles.com (CPO OR optical interconnect OR silicon photonics OR optical networking)'),
    ("国外·TheElec", 'site:thelec.net (CPO OR silicon photonics OR optical interconnect OR glass substrate OR TGV)'),
    ("国外·ETNews", 'site:etnews.com OR site:en.etnews.com (CPO OR silicon photonics OR optical interconnect OR glass substrate OR TGV)'),
    ("国外·NikkeiAsia", 'site:asia.nikkei.com (CPO OR silicon photonics OR optical interconnect OR glass substrate)'),
    ("国外·TechPowerUp", 'site:techpowerup.com (CPO OR silicon photonics OR optical interconnect OR optical I/O)'),
    ("国外·AnandTech", 'site:anandtech.com (CPO OR silicon photonics OR optical interconnect)'),

    # 企业官网
    ("国外·NVIDIA", 'site:nvidia.com (CPO OR silicon photonics OR optical networking OR optical interconnect OR Spectrum-X)'),
    ("国外·Broadcom", 'site:broadcom.com (CPO OR co-packaged optics OR silicon photonics OR optical engine OR Tomahawk)'),
    ("国外·Intel", 'site:intel.com (silicon photonics OR optical I/O OR glass substrate OR glass core substrate)'),
    ("国外·AMD", 'site:amd.com (optical interconnect OR silicon photonics OR CPO)'),
    ("国外·Marvell", 'site:marvell.com (CPO OR silicon photonics OR optical interconnect OR 1.6T OR DSP)'),
    ("国外·Cisco", 'site:cisco.com (CPO OR silicon photonics OR optical interconnect OR optical networking)'),
    ("国外·Coherent", 'site:coherent.com (CPO OR optical engine OR silicon photonics OR 1.6T OR CW laser)'),
    ("国外·Lumentum", 'site:lumentum.com (CPO OR CW laser OR optical interconnect OR 1.6T OR photonics)'),
    ("国外·Corning", 'site:corning.com (glass substrate OR glass interposer OR optical interconnect) semiconductor'),
    ("国外·AppliedMaterials", 'site:appliedmaterials.com (glass substrate OR silicon photonics OR advanced packaging)'),
    ("国外·TSMC", 'site:tsmc.com (silicon photonics OR CPO OR COUPE OR photonics)'),
    ("国外·Samsung", 'site:samsung.com OR site:samsungsem.com (glass core substrate OR silicon photonics OR optical interconnect)'),
    ("国外·GlobalFoundries", 'site:gf.com (silicon photonics OR optical interconnect OR CPO)'),
    ("国外·TowerSemiconductor", 'site:towersemi.com (silicon photonics OR SiPho OR optical)'),
    ("国外·AyarLabs", 'site:ayarlabs.com (optical I/O OR optical interconnect OR CPO)'),
    ("国外·Lightmatter", 'site:lightmatter.co (optical interconnect OR Passage OR photonic)'),
    ("国外·CelestialAI", 'site:celestial.ai (optical interconnect OR photonic fabric)'),
    ("国外·Ranovus", 'site:ranovus.com (CPO OR optical engine OR silicon photonics)'),

    # 会议/机构/研究
    ("国外·OFC", 'site:ofcconference.org (CPO OR optical interconnect OR silicon photonics OR optical I/O OR 1.6T)'),
    ("国外·OIF", 'site:oiforum.com (CPO OR "optical I/O" OR "co-packaged optics" OR 1.6T OR CEI)'),
    ("国外·CXLConsortium", 'site:computeexpresslink.org (optical OR photonic OR interconnect OR scale-up)'),
    ("国外·EthernetAlliance", 'site:ethernetalliance.org (optical OR 800G OR 1.6T OR CPO OR LPO)'),
    ("国外·OpenCompute", 'site:opencompute.org (optical interconnect OR CPO OR silicon photonics OR optical I/O)'),
    ("国外·ECOC", 'site:ecoc.org OR site:ecoc2026.org (CPO OR optical interconnect OR silicon photonics OR 1.6T)'),
    ("国外·ECTC", 'site:ectc.net (TGV OR glass substrate OR glass core substrate OR photonics)'),
    ("国外·IEEE", 'site:ieee.org (CPO OR optical interconnect OR silicon photonics OR glass core substrate OR TGV)'),
    ("国外·Optica", 'site:optica.org (CPO OR optical interconnect OR silicon photonics OR optical I/O)'),
    ("国外·SPIE", 'site:spie.org (CPO OR optical interconnect OR silicon photonics OR optical I/O OR TGV)'),
    ("国外·imec", 'site:imec-int.com (silicon photonics OR optical interconnect OR glass substrate OR photonics)'),
    ("国外·IMAPS", 'site:imaps.org (glass substrate OR through-glass via OR photonics OR optical interconnect)'),
    ("国外·arXiv", 'site:arxiv.org ("optical interconnect" OR "optical I/O" OR "silicon photonics" OR "co-packaged optics" OR "glass core substrate")'),
]

TOPIC_TERMS = {
    "TGV/玻璃基板": ["through-glass via","through glass via","glass core substrate","glass-core substrate","glass interposer","玻璃通孔","玻璃互连孔","玻璃芯基板","玻璃中介层"],
    "CPO/NPO/LPO": ["co-packaged optics","near-packaged optics","linear pluggable optics","共封装光学","近封装光学","线性可插拔","cpo","npo","lpo","lro"],
    "AI光互联": ["optical interconnect","optical i/o","optical io","光互联","光互连","光互連","scale-up","scale-out","gpu interconnect"],
    "硅光/光引擎": ["silicon photonics","silicon photonic","siph","optical engine","photonic integrated circuit","硅光","硅光子","矽光","光引擎"],
    "光芯片/器件": ["cw laser","dfb","eml","vcsel","thin film lithium niobate","tfln","磷化铟","光芯片","激光器","调制器"],
    "高速光模块": ["800g","1.6t","3.2t","400g/lane","200g/lane","optical transceiver","optical module","光模块"],
    "OCS/光交换": ["optical circuit switch","all-optical switching","光路交换","光电路交换","全光交换","ocs"],
    "MicroLED光互联": ["micro-led","microled"],
}
CONTEXT_TERMS = ["ai","datacenter","data center","gpu","accelerator","switch","ethernet","optical","photon","semiconductor","packaging","光","算力","数据中心","交换机","半导体","封装"]

def clean(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()

def parse_date(value):
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return ""

def topic_for(text):
    t=(text or "").lower()
    hits=[]
    for topic, terms in TOPIC_TERMS.items():
        for term in terms:
            # Very short acronyms need token boundaries to avoid false positives.
            if len(term) <= 4 and term.isascii() and term.replace("-","").isalnum():
                if re.search(r"(?<![a-z0-9])"+re.escape(term)+r"(?![a-z0-9])", t):
                    hits.append(topic); break
            elif term in t:
                hits.append(topic); break
    if "光芯片/器件" in hits and not any(k in t for k in CONTEXT_TERMS):
        hits.remove("光芯片/器件")
    if "MicroLED光互联" in hits and not any(k in t for k in ["optical","光互联","光互连","光通信","photon"]):
        hits.remove("MicroLED光互联")
    return hits

def is_relevant(text):
    return bool(topic_for(text))

A_TIER_SOURCES = [
    "DigiTimes","EE Times","Semiconductor Engineering","TechInsights","Yole",
    "TrendForce","LightCounting","Omdia","NVIDIA","Broadcom","Intel","AMD","Marvell",
    "Cisco","Coherent","Lumentum","TSMC","GlobalFoundries","Tower Semiconductor",
    "Ayar Labs","Lightmatter","Celestial AI","Ranovus","OFC","OIF","IEEE","Optica","SPIE","imec"
]
B_TIER_SOURCES = [
    "The Elec","ETNews","Lightwave","Fibre Systems","Photonics Spectra",
    "Data Center Dynamics","ServeTheHome","SemiAnalysis","SemiWiki","Tom's Hardware",
    "TechPowerUp","AnandTech","3DInCites","IMAPS","ECTC","C114","爱集微",
    "电子工程专辑","OFweek","通信世界","通信产业网","电子发烧友","与非网","21ic","EEWorld"
]

def source_tier(source, group=""):
    s=(source+" "+group).lower()
    if any(x.lower() in s for x in A_TIER_SOURCES):
        return "A"
    if any(x.lower() in s for x in B_TIER_SOURCES):
        return "B"
    return "C"

def intelligence_value(text, source_grade):
    t=(text or "").lower()
    strong_terms=[
        "mass production","volume production","qualification","customer validation","shipment",
        "design win","order","capacity","pilot line","production line","partnership","launch",
        "量产","客户验证","送样","订单","扩产","产线","投产","签约","发布","首发","突破"
    ]
    technical_terms=[
        "1.6t","3.2t","200g/lane","400g/lane","cpo","co-packaged optics","optical i/o",
        "silicon photonics","glass core substrate","through-glass via","tfln",
        "1.6T","3.2T","CPO","硅光","玻璃芯基板","玻璃通孔","薄膜铌酸锂"
    ]
    strong=sum(1 for k in strong_terms if k in t)
    tech=sum(1 for k in technical_terms if k.lower() in t)
    score=(30 if source_grade=="A" else 18 if source_grade=="B" else 8) + strong*12 + min(tech,3)*8
    if score >= 65:
        return "重点情报", min(score,100)
    if score >= 42:
        return "值得关注", min(score,100)
    return "一般资讯", min(score,100)

def insight_fields(title, summary, category, value_level):
    text=(title or "").strip()
    summary=(summary or "").strip()
    event=text if text else "暂无明确事件标题"
    key=summary[:180] if summary else ("该条属于"+category+"，需打开原文确认核心事实与参数。")
    if value_level=="重点情报":
        impact="可能影响技术路线、供应链格局、客户验证或量产节奏，建议优先核验原文。"
    elif value_level=="值得关注":
        impact="对相关技术方向和产业进展具有参考价值，建议结合后续进展持续跟踪。"
    else:
        impact="作为行业背景信息参考，当前未识别到明确量产、订单或客户验证信号。"
    return event, key, impact

def classify(text):
    t=(text or "").lower()
    if any(k in t for k in ["process","fabrication","laser drilling","etching","metallization","plating","modulator","architecture","工艺","激光","蚀刻","金属化","电镀","架构","调制"]):
        return "技术进展"
    if any(k in t for k in ["production","capacity","investment","qualification","customer","shipment","order","partnership","量产","产线","扩产","投资","客户验证","订单","合作"]):
        return "产业进展"
    if any(k in t for k in ["paper","research","conference","patent","论文","研究","会议","专利"]):
        return "研发/会议"
    return "行业资讯"

def needs_translation(text):
    if not text: return False
    latin=len(re.findall(r"[A-Za-z]",text))
    cjk=len(re.findall(r"[\u4e00-\u9fff]",text))
    return latin >= 8 and latin > cjk*1.5

def translate_zh(text):
    if not text or not needs_translation(text):
        return text
    try:
        q=urllib.parse.urlencode({"client":"gtx","sl":"auto","tl":"zh-CN","dt":"t","q":text[:700]})
        req=urllib.request.Request(TRANSLATION_ENDPOINT+"?"+q,headers=HEADERS)
        with urllib.request.urlopen(req,timeout=3) as r:
            data=json.load(r)
        out="".join(p[0] for p in data[0] if p and p[0]).strip()
        return out if out else text
    except Exception:
        return text

def fetch_google(group, query, source_type, chinese=False):
    edition="&hl=zh-CN&gl=CN&ceid=CN:zh-Hans" if chinese else "&hl=en-US&gl=US&ceid=US:en"
    url="https://news.google.com/rss/search?q="+urllib.parse.quote(query)+edition
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=12) as r:
        root=ET.fromstring(r.read())
    rows=[]
    for item in root.findall(".//item")[:100]:
        title=clean(item.findtext("title"))
        summary=clean(item.findtext("description"))
        link=(item.findtext("link") or "").strip()
        source=clean(item.findtext("source")) or group
        if summary == title: summary=""
        text=title+" "+summary+" "+query
        if not title or not link or not is_relevant(text):
            continue
        rows.append({
            "source_group":group, "source_type":source_type, "source":source,
            "original_title":title, "original_summary":summary,
            "date":parse_date(item.findtext("pubDate") or ""), "url":link,
            "topics":topic_for(title+" "+summary+" "+query)
        })
    return rows

def fetch_bing_news(group, query, source_type, chinese=False):
    market = "zh-CN" if chinese else "en-US"
    url = "https://www.bing.com/news/search?" + urllib.parse.urlencode({
        "q": query, "format": "rss", "setlang": market
    })
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=12) as r:
        root = ET.fromstring(r.read())
    rows = []
    for item in root.findall(".//item")[:80]:
        title = clean(item.findtext("title"))
        summary = clean(item.findtext("description"))
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        source = clean(item.findtext("source")) or group
        if summary == title:
            summary = ""
        text = title + " " + summary + " " + query
        if not is_relevant(text):
            continue
        rows.append({
            "source_group": group + "·Bing",
            "source_type": source_type,
            "source": source,
            "original_title": title,
            "original_summary": summary,
            "date": parse_date(item.findtext("pubDate") or ""),
            "url": link,
            "topics": topic_for(text)
        })
    return rows

def collect():
    jobs = []
    rows = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for g, q in DOMESTIC_QUERIES:
            jobs.append(pool.submit(fetch_google, g, q, "国内网站", True))
            jobs.append(pool.submit(fetch_bing_news, g, q, "国内网站", True))
        for g, q in FOREIGN_QUERIES:
            jobs.append(pool.submit(fetch_google, g, q, "国外网站", False))
            jobs.append(pool.submit(fetch_bing_news, g, q, "国外网站", False))
        for f in as_completed(jobs):
            try:
                rows.extend(f.result())
            except Exception as exc:
                print("检索失败：", str(exc)[:120])
    return rows

def load_previous():
    try:
        with open(DATA_FILE,"r",encoding="utf-8") as f:
            d=json.load(f)
        return d.get("news",[]) if isinstance(d.get("news"),list) else []
    except Exception:
        return []

def main():
    previous=load_previous()
    rows=collect()

    # URL + normalized title双重去重，减少同一新闻被多个查询重复收录。
    seen_urls=set()
    seen_titles=set()
    dedup=[]
    for r in sorted(rows,key=lambda x:x.get("date",""),reverse=True):
        nt=re.sub(r"[^a-z0-9\u4e00-\u9fff]+","",r["original_title"].lower())
        if r["url"] in seen_urls or (nt and nt in seen_titles):
            continue
        seen_urls.add(r["url"]); seen_titles.add(nt); dedup.append(r)

    # 翻译仅用于最近国外标题，翻译失败直接保留英文，不影响采集。
    foreign=[r for r in dedup if r["source_type"]=="国外网站"]
    foreign.sort(key=lambda x:x.get("date",""),reverse=True)
    translate_ids=set(id(x) for x in foreign[:100])

    news=[]
    for r in dedup:
        raw_title=r["original_title"]
        title=translate_zh(raw_title) if id(r) in translate_ids else raw_title
        category=classify(raw_title+" "+r["original_summary"])
        grade=source_tier(r["source"], r["source_group"])
        value_level,value_score=intelligence_value(raw_title+" "+r["original_summary"], grade)
        event,key_point,impact=insight_fields(title, r["original_summary"], category, value_level)
        news.append({
            "title":title,
            "original_title":raw_title,
            "summary":r["original_summary"],
            "original_summary":r["original_summary"],
            "date":r["date"],
            "source":r["source"],
            "source_group":r["source_group"],
            "source_type":r["source_type"],
            "source_grade":grade,
            "value_level":value_level,
            "value_score":value_score,
            "event":event,
            "key_point":key_point,
            "impact":impact,
            "category":category,
            "url":r["url"],
            "translation_status":"已翻译标题" if title != raw_title else "原文",
            "topics":r["topics"],
            "relevance_level":"核心相关",
        })

    # 保留此前仍在监测范围内、且180天以内的历史记录，避免每天刷新造成归档骤减。
    known={n["url"] for n in news}
    for old in previous:
        if not isinstance(old,dict) or not old.get("url") or old["url"] in known:
            continue
        text=" ".join(str(old.get(k,"")) for k in ("title","original_title","summary","original_summary","source_group"))
        topics=topic_for(text)
        if not topics:
            continue
        old["topics"]=topics
        old["source_grade"]=old.get("source_grade") or source_tier(str(old.get("source","")), str(old.get("source_group","")))
        if not old.get("value_level"):
            vl,vs=intelligence_value(text, old["source_grade"])
            old["value_level"]=vl; old["value_score"]=vs
            ev,kp,im=insight_fields(str(old.get("title") or old.get("original_title") or ""), str(old.get("summary") or old.get("original_summary") or ""), str(old.get("category") or "行业资讯"), vl)
            old["event"]=ev; old["key_point"]=kp; old["impact"]=im
        if old.get("source_type") not in ("国内网站","国外网站"):
            # 基于是否主要为中文来归入国内/国外，历史记录只作补充。
            cjk=len(re.findall(r"[\u4e00-\u9fff]",text))
            latin=len(re.findall(r"[A-Za-z]",text))
            old["source_type"]="国内网站" if cjk >= latin*0.3 else "国外网站"
        news.append(old); known.add(old["url"])

    cutoff=datetime.now(timezone.utc).timestamp()-180*86400
    kept=[]
    for n in news:
        try:
            ts=datetime.strptime(n.get("date",""),"%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
            if ts >= cutoff:
                kept.append(n)
        except Exception:
            pass

    kept.sort(key=lambda x:(x.get("value_score",0),x.get("date","")),reverse=True)
    kept=kept[:4000]
    tmp=DATA_FILE+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump({
            "updated_at":datetime.now(timezone.utc).isoformat(),
            "scope":"TGV + AI高速光互联全链路；国内网站 + 国外网站；无微信公众号采集",
            "news":kept
        },f,ensure_ascii=False,indent=2)
    os.replace(tmp,DATA_FILE)

    cn=sum(1 for n in kept if n.get("source_type")=="国内网站")
    foreign_n=sum(1 for n in kept if n.get("source_type")=="国外网站")
    topic_stats={k:sum(1 for n in kept if k in n.get("topics",[])) for k in TOPIC_TERMS}
    print(f"完成：归档 {len(kept)} 条；国内网站 {cn} 条；国外网站 {foreign_n} 条。")
    print("主题："+"；".join(f"{k} {v}" for k,v in topic_stats.items()))

if __name__=="__main__":
    main()
