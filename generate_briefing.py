"""generate_briefing.py - 凌晨运行，筛选+AI摘要+政治经济学评论，产出简报文件
北京时间00:30触发，只处理前一日抓取的文章。
产出: articles/daily/{date}_briefing.json
"""
import requests, re, json, os, time, glob
from datetime import datetime, timedelta, timezone

MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_BASE_URL = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_MODEL = os.environ.get("MIMO_MODEL", "mimo-v2.5")

# ============ 政治经济学经典文献引用库 ============
POL_ECON_QUOTES = {
    "劳动价值论": [
        {"text": "商品首先是一个外界的对象，一个靠自己的属性来满足人的某种需要的物。商品的二重性在于：作为使用价值，它满足人的需要；作为价值，它是人类无差别劳动的结晶。使用价值是价值的物质承担者。价值量由生产该商品所需要的社会必要劳动时间决定。金银天然不是货币，但货币天然是金银。货币作为价值尺度，是商品内在的价值尺度即劳动时间的必然表现形式。价格是价值的货币表现。商品的价格围绕着价值上下波动，不是违反价值规律，恰恰是价值规律发挥作用的形式。", "source": "资本论第一卷·第一篇"}
    ],
    "剩余价值与剥削": [
        {"text": "劳动力的使用就是劳动本身。劳动力的买者消费劳动力，就是叫劳动力的卖者劳动。价值增殖过程不外是超过一定点而延长了的价值形成过程。如果价值形成过程只持续到这样一点，即资本所支付的劳动力价值恰好为新的等价物所补偿，那就是单纯的价值形成过程。如果价值形成过程超过这一点而继续下去，那就成为价值增殖过程。资本主义生产不仅是商品的生产，它实质上是剩余价值的生产。", "source": "资本论第一卷·第五章"},
        {"text": "一切劳动，一方面是人类劳动力在生理学意义上的耗费；就相同的或抽象的人类劳动这个属性来说，它形成商品价值。一切劳动，另一方面是人类劳动力在特殊的有一定目的的形式上的耗费；就具体的有用的劳动这个属性来说，它生产使用价值。劳动的二重性是理解政治经济学的枢纽。", "source": "资本论第一卷·第一章"},
        {"text": "资本由于无限度地盲目追逐剩余劳动，像狼一般地贪求剩余劳动，不仅突破了工作日的道德极限，而且突破了工作日的纯粹身体的极限。它侵占人体的成长、发育和维持健康所需的时间。它掠夺工人呼吸新鲜空气和接触阳光所需要的时间。它克扣吃饭时间，尽量把吃饭时间并入生产过程，因此对工人来说就像对待一台机器那样，给他喂食就是给机器加油一样。", "source": "资本论第一卷·第八章"}
    ],
    "工资理论": [
        {"text": "工资不是它表面上呈现的那种东西，不是劳动的价值或价格，而只是劳动力的价值或价格的掩蔽形式。工资的形式消灭了工作日分为必要劳动和剩余劳动、分为有酬劳动和无酬劳动的一切痕迹，全部劳动都表现为有酬劳动。这种虚假的外观使雇佣工人的地位和奴隶的地位相比，反而有了更大的欺骗性。决定工资的一般变动的，不是工人人口绝对数量的增减，而是工人阶级分为现役劳动军和产业后备军的变动。", "source": "资本论第一卷·第十七章、第二十三章"}
    ],
    "资本积累与贫困化": [
        {"text": "社会的财富即执行职能的资本越大，它的增长的规模和能力越大，从而无产阶级的绝对数量和他们的劳动生产力越大，产业后备军也就越大。可供支配的劳动力同资本的膨胀力一样，是由同一些原因发展起来的。产业后备军的相对量和财富的力量一同增长。但是同现役劳动军相比，这种后备军越大，常备的过剩人口也就越多，他们的贫困同他们所受的劳动折磨成反比。这就是资本主义积累的绝对的、一般的规律。", "source": "资本论第一卷·第二十三章"},
        {"text": "所谓原始积累只不过是生产者和生产资料分离的历史过程。劳动者只有当他不再束缚于土地，不再隶属或从属他人的时候，才能支配自身。这种剥夺的历史是用血和火的文字载入人类编年史的。资本来到世间，从头到脚，每个毛孔都滴着血和肮脏的东西。从资本主义生产方式产生的资本主义占有方式，是对个人的、以自己劳动为基础的私有制的第一个否定。但资本主义生产由于自然过程的必然性，造成了对自身的否定。资本主义私有制的丧钟就要响了。剥夺者就要被剥夺了。", "source": "资本论第一卷·第二十四章"}
    ],
    "分工与协作": [
        {"text": "较多的工人在同一时间、同一空间，为了生产同种商品，在同一资本家的指挥下工作，这在历史上和逻辑上都是资本主义生产的起点。协作不仅提高了个人生产力，而且创造了一种新的生产力，这种生产力本身必然是集体力。工场手工业分工通过手工业活动的分解、劳动工具的专门化，造成了社会生产过程的质的划分和量的比例，创立了社会劳动的一定组织，这样就同时发展了新的、社会的劳动生产力。但工场手工业同时也损害了工人的整个劳动能力，使工人畸形发展。机器大工业使工人从机器的附属物变成了机器体系的附属物。", "source": "资本论第一卷·第十一至十三章"}
    ],
    "利润率下降与经济危机": [
        {"text": "利润率趋向下降的规律，无非是说，随着资本主义生产方式的发展，资本有机构成不断提高，利润率也就必然趋于下降。这种下降趋势是资本主义生产方式内在矛盾的表现。资本主义生产的真正限制就是资本本身。危机永远只是现有矛盾的暂时的暴力的解决，永远只是使已经破坏的平衡得到瞬间恢复的暴力的爆发。生产过剩的危机是资本主义生产方式特有的现象。生产的限制是资本的限制。", "source": "资本论第三卷·第三篇、第十五章"},
        {"text": "信用制度加速了生产力的物质上的发展和世界市场的形成，使这二者作为新生产形式的物质基础发展到一定的高度，是资本主义生产方式的历史使命。同时，信用也是加速这种矛盾爆发的手段，即加速旧生产方式解体的手段。信用制度在资本主义体系中成为使资本主义生产方式转到一种新生产方式的过渡形式。生息资本从其最初的形态到它的高度发达的形态，同资本的现实运动相比，不过是一种巨大的虚构。", "source": "资本论第三卷·第二十五章、第三十二章"}
    ],
    "虚拟资本与金融化": [
        {"text": "人们把虚拟资本的形成叫作资本化。人们把每一个有规则的会反复取得的收入按平均利息率来计算，把它算作是按这个利息率贷出的资本会提供的收益，这样就把这个收入资本化了。国债、股票等有价证券都是虚拟资本，它们只是代表取得收益的权利，并不代表现实资本。虚拟资本的增加并不等于现实财富的增加，但虚拟资本的剧烈波动却能深刻影响现实经济。利息实际上是利润的一部分，是剩余价值的转化形式。", "source": "资本论第三卷·第二十九章"}
    ],
    "资本流通与再生产": [
        {"text": "资本的流通时间，一般说来，会限制资本的生产时间，从而也会限制它的价值增殖过程。流通时间越是等于零或近于零，资本的职能就越大，资本的生产效率就越高。社会资本再生产的核心问题是社会总产品的实现条件：简单再生产要求第一部类的可变资本加剩余价值等于第二部类的不变资本，扩大再生产则要求前者大于后者。货币资本在社会资本再生产过程中起着重要的作用。", "source": "资本论第二卷·第五章、第三篇"}
    ],
    "地租理论": [
        {"text": "级差地租本质上是由投在最坏土地上的资本的收益决定的，较好土地上的超额利润转化为地租归土地所有者占有。绝对地租则来自农产品价值超过生产价格的那部分余额，由于农业资本有机构成低于工业，农产品按价值出售就会产生一个超过生产价格的余额，这个余额由于土地所有权的垄断而被截留为绝对地租。土地价格是资本化的地租。", "source": "资本论第三卷·第六篇"}
    ],
    "帝国主义": [
        {"text": "帝国主义是资本主义的最高阶段。帝国主义在经济方面的基本特征就是资本主义的垄断代替了自由竞争。垄断是从自由竞争中成长起来的，是自由竞争的直接对立物，但是垄断并不消除竞争，而是凌驾于竞争之上，与之并存，因而产生许多特别尖锐、特别剧烈的矛盾和冲突。帝国主义是垄断的资本主义、寄生或腐朽的资本主义、垂死的资本主义。垄断资本主义使资本主义的一切矛盾尖锐到了极点，使无产阶级革命成为不可避免。", "source": "列宁·帝国主义是资本主义的最高阶段"},
        {"text": "生产集中产生垄断，是现阶段资本主义发展的一般的和基本的规律。自由竞争引起生产集中，而生产集中发展到一定阶段就必然引起垄断。随着银行和工业日益融合，形成了金融资本。金融资本的垄断统治是帝国主义最重要的特征之一。少数积累了巨额资本的最富国家处于垄断地位，形成了大量过剩资本，必须输出到国外去攫取更高的利润。资本输出成为帝国主义的重要特征。垄断组织和国家政权相结合，又形成国家垄断资本主义，为向社会主义过渡准备了最完备的物质条件。", "source": "列宁·帝国主义论"}
    ],
    "分配与生产关系": [
        {"text": "在分配是产品的分配之前，它首先是生产资料的分配，是生产工具的分配，是社会成员在各类生产中的分配。这种分配包含在生产过程本身中并且决定生产的结构，产品的分配显然只是这种分配的结果。分配关系本质上和生产关系是同一的，是生产关系的反面。一定的分配形式是以一定的生产形式为条件的，分配形式的变化不过是生产形式变化的结果。", "source": "马克思·政治经济学批判·导言"},
        {"text": "商品流通是资本的起点。商品生产和发达的商品流通，即贸易，是资本产生的历史前提。如果撇开商品流通的物质内容，只考察这一过程的经济形式，那么货币就是这一过程的最后产物。商品流通的这个最后产物是资本的最初的表现形式。资本不能从流通中产生，又不能不从流通中产生。它必须既在流通中又不在流通中产生。", "source": "资本论第一卷·第四章"}
    ]
}

def get_relevant_quotes(article_text, max_quotes=2):
    keyword_topics = {
        "劳动价值论": ["value", "price", "market", "commodity", "trade", "价值", "价格", "市场", "商品"],
        "剩余价值与剥削": ["profit", "exploitation", "surplus", "labor", "worker", "working", "wage", "剥削", "剩余价值", "劳动力", "工作日"],
        "工资理论": ["wage", "salary", "income", "pay", "minimum wage", "工资", "薪酬", "收入"],
        "资本积累与贫困化": ["accumulation", "poverty", "inequality", "wealth", "concentration", "积累", "贫困", "贫富", "不平等", "财富"],
        "分工与协作": ["automation", "AI", "machine", "technology", "manufacturing", "factory", "自动化", "机器", "制造业", "技术"],
        "利润率下降与经济危机": ["crisis", "recession", "downturn", "credit", "finance", "bubble", "危机", "衰退", "信贷", "金融", "泡沫"],
        "虚拟资本与金融化": ["stock", "bond", "securities", "virtual", "capital market", "debt", "股票", "债券", "证券", "资本市场", "债务"],
        "资本流通与再生产": ["supply chain", "circulation", "reproduction", "供应链", "流通", "再生产"],
        "地租理论": ["land", "rent", "housing", "real estate", "property", "土地", "租金", "住房", "房地产", "拆迁"],
        "帝国主义": ["imperialism", "empire", "colony", "hegemony", "sanction", "tariff", "trade war", "资本输出", "垄断", "帝国主义", "制裁", "关税", "贸易战"],
        "分配与生产关系": ["distribution", "redistribution", "production", "分配", "生产", "所有制"]
    }
    body_lower = article_text[:2000].lower()
    scored = []
    for topic, keywords in keyword_topics.items():
        score = sum(1 for kw in keywords if kw.lower() in body_lower)
        if score > 0:
            scored.append((score, topic))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = []
    for _, topic in scored[:max_quotes]:
        if topic in POL_ECON_QUOTES:
            selected.append(POL_ECON_QUOTES[topic][0])
    return selected if selected else [POL_ECON_QUOTES["剩余价值与剥削"][0]]

def is_deep_report(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    if "fulltext_deep" in content:
        return True
    m = re.search(r'(\d+)\s*words', content)
    if m and int(m.group(1)) >= 300:
        return True
    return False

def get_article_info(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    title_m = re.search(r'<title>(.*?)</title>', content)
    title = title_m.group(1).strip() if title_m else os.path.basename(filepath)
    url_m = re.search(r'href="(https?://[^"]+)"', content.split("原文")[-1] if "原文" in content else content)
    url = url_m.group(1) if url_m else ""
    body_div = re.findall(r'<p>(.*?)</p>', content, re.DOTALL)
    body = "\n".join([re.sub(r'<[^>]+>', '', p).strip() for p in body_div if p.strip()])
    wc = len(re.findall(r'[a-zA-Z]+', body))
    return {"title": title, "body": body, "url": url, "word_count": wc, "filepath": filepath}

def filter_articles(base_dir, target_date):
    """只处理target_date当天抓取的文章（通过文件名日期前缀判断）。
    target_date格式: YYYY-MM-DD
    """
    target_prefix = target_date.replace("-", "")  # 20260627
    caixin_dir = os.path.join(base_dir, "articles")
    scmp_dir = os.path.join(base_dir, "articles/scmp")
    deep_articles = []
    
    # DEBUG: check directories
    for d in [caixin_dir, scmp_dir]:
        exists = os.path.exists(d)
        count = len(glob.glob(os.path.join(d, "*.html"))) if exists else 0
        print(f"  [DEBUG] {d}: exists={exists}, html_count={count}")
    for search_dir, source in [(caixin_dir, "caixin"), (scmp_dir, "scmp")]:
        if not os.path.exists(search_dir):
            continue
        html_files = glob.glob(os.path.join(search_dir, "*.html"))
        for fp in html_files:
            fname = os.path.basename(fp)
            # 检查文件名是否以目标日期开头
            if fname.startswith(target_prefix):
                pass  # date prefix match
            elif source == "scmp":
                # SCMP old format (scmp_xxx.html) has no date prefix - extract from HTML meta
                try:
                    with open(fp, "r", encoding="utf-8") as hf:
                        meta_m = re.search(r"\|(\d{4}-\d{2}-\d{2})\|", hf.read(500))
                    if meta_m:
                        file_date = meta_m.group(1).replace("-", "")
                        # Accept target_date or target_date-1 (UTC/BJT timezone gap)
                        dt_target = datetime.strptime(target_date, "%Y-%m-%d")
                        dt_minus1 = (dt_target - timedelta(days=1)).strftime("%Y%m%d")
                        if file_date != target_prefix and file_date != dt_minus1:
                            continue
                    else:
                        continue
                except:
                    continue
            else:
                continue
            if is_deep_report(fp):
                info = get_article_info(fp)
                info["source"] = source
                deep_articles.append(info)
                print(f"  [KEEP] {fname} ({info['word_count']} words)")
            else:
                os.remove(fp)
                print(f"  [DEL] 非深度: {fname}")
    return deep_articles

def call_mimo(prompt, max_tokens=2000, retry_on_reject=True):
    """Call mimo API. Returns text or None. Detects content moderation rejection."""
    try:
        resp = requests.post(
            f"{MIMO_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {MIMO_API_KEY}", "Content-Type": "application/json"},
            json={"model": MIMO_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": 0.7},
            timeout=120
        )
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"].strip()
            # Detect content moderation rejection
            reject_keywords = ["high risk", "rejected", "blocked", "content policy", "violates"]
            if any(kw in text.lower() for kw in reject_keywords):
                print(f"  [MIMO] Content rejected by moderation, using fallback")
                return None
            return text
        elif resp.status_code == 400 and retry_on_reject:
            # Try with a safer prompt (strip the article body, keep only title)
            print(f"  [MIMO] API 400, trying safer prompt...")
            safe_prompt = prompt.split("Article:")[-1] if "Article:" in prompt else prompt
            return call_mimo(f"Summarize this in 2-3 sentences: {safe_prompt[:1000]}", max_tokens=max_tokens // 2, retry_on_reject=False)
        else:
            print(f"  [MIMO] API error {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  [MIMO] error: {e}")
        return None

def extractive_summary(article):
    """Fallback: extract first 3-5 meaningful sentences from article body."""
    body = article.get("body", "")
    # Split by sentence-ending punctuation
    sentences = re.split(r'(?<=[.!?])\s+', body)
    meaningful = [s.strip() for s in sentences if len(s.strip()) > 40 and not s.strip().startswith("<")]
    selected = meaningful[:5]
    result = "\n".join([f"- {s}" for s in selected])
    # Truncate to ~300 chars
    if len(result) > 300:
        result = result[:300] + "..."
    return result

def generate_english_summary(article):
    body = article["body"][:3000]
    prompt = f"""Summarize the following article in 3-5 concise bullet points in English. Focus on key facts, data, and analysis. Do not add commentary.

Title: {article['title']}

Article:
{body}"""
    result = call_mimo(prompt, max_tokens=500)
    if not result:
        # Fallback: extractive summary
        result = extractive_summary(article)
    return result

def generate_left_wing_commentary(article):
    body = article["body"][:4000]
    quotes = get_relevant_quotes(body, max_quotes=2)
    quotes_text = "\n\n".join([f"【{q['source']}】{q['text']}" for q in quotes])
    prompt = f"""你是一名精通马克思主义政治经济学的左翼学者。请对以下新闻文章从政治经济学角度撰写一篇600-800字的中文评论。

分析框架：
1. 现象描述（简述核心事实，50字以内）
2. 政治经济学定位（从生产关系、交换关系、分配关系、资本运动等维度切入）
3. 深层结构分析（揭示现象背后的阶级关系、利益结构和制度性原因）
4. 阶级/利益分析（谁受益、谁受损、权力如何流动）
5. 主流叙事批判（主流媒体/官方话语如何掩盖矛盾实质）
6. 解放前景（从政治经济学角度指出可能的出路或变革方向）

严格要求：
- 必须直接引用下方提供的经典文献原文，引用时标注出处
- 分析仅限政治经济学范畴（生产、流通、分配、资本积累、危机、垄断、地租等），不要涉及意识形态批判、哲学思辨或文化分析
- 引用要有机融入分析，不要生硬粘贴
- 语言学术但不晦涩，面向受过良好教育的读者

可引用的经典文献：
{quotes_text}

文章标题: {article['title']}

文章正文:
{body}"""
    result = call_mimo(prompt, max_tokens=2000)
    if not result:
        # Fallback: brief extractive commentary
        result = f"（AI摘要生成被内容审核拒绝，以下为简要提取）\n\n{article['title']}\n\n"
        result += extractive_summary(article)
    return result

def select_best_for_analysis(articles):
    keywords = ["worker", "labor", "capital", "class", "inequality", "poverty",
                "protest", "strike", "unemployment", "wage", "migrant",
                "corruption", "land", "housing", "debt", "austerity",
                "AI", "automation", "tech", "platform", "gig",
                "energy", "carbon", "trade war", "tariff", "sanction",
                "semiconductor", "stock", "market", "finance", "banking",
                "reform", "privatization", "state-owned", "SOE",
                "imperialism", "hegemony", "monopoly"]
    scored = []
    for a in articles:
        title_lower = a["title"].lower()
        body_lower = a["body"][:1000].lower()
        score = 0
        for kw in keywords:
            if kw.lower() in title_lower: score += 3
            if kw.lower() in body_lower: score += 1
        if "in depth" in title_lower or "analysis" in title_lower: score += 2
        scored.append((score, a))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else None

def main():
    base_dir = "."
    now = datetime.now(timezone.utc)
    bj_time = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    date_str = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    # 默认处理前一天，可通过TARGET_DATE环境变量覆盖
    target = os.environ.get("TARGET_DATE", "")
    if target:
        target_date = target
    else:
        target_date = (now - timedelta(days=1)).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    print(f"=== 生成简报 {bj_time} (处理 {target_date} 的文章) ===")

    # Phase 1: 过滤非深度报道（仅前一天日期的文章）
    print(f"\n[Phase 1] 筛选 {target_date} 的深度报道...")
    deep_articles = filter_articles(base_dir, target_date)
    print(f"  深度报道: {len(deep_articles)} 篇")

    if not deep_articles:
        print("  无深度报道，生成空简报")
        briefing_data = {"date": date_str, "articles": [], "commentary": "", "commentary_title": ""}
    else:
        # Phase 2: AI生成英文摘要
        print(f"\n[Phase 2] 生成英文摘要 ({len(deep_articles)} 篇)...")
        for a in deep_articles:
            print(f"  摘要: {a['title'][:50]}...")
            a["summary"] = generate_english_summary(a) or ""
            if a["summary"]: print(f"    OK ({len(a['summary'])} chars)")
            else: print(f"    FAIL")
            time.sleep(2)

        # Phase 3: 政治经济学评论
        print("\n[Phase 3] 生成政治经济学评论...")
        best = select_best_for_analysis(deep_articles)
        left_commentary = ""
        commentary_title = ""
        if best:
            commentary_title = best["title"]
            print(f"  选中: {commentary_title[:60]}")
            left_commentary = generate_left_wing_commentary(best) or ""
            if left_commentary: print(f"    OK ({len(left_commentary)} chars)")
            else: print(f"    FAIL")
        else:
            left_commentary = "未找到适合政治经济学分析的文章。"

        briefing_data = {
            "date": date_str,
            "articles": [
                {
                    "title": a["title"],
                    "source": a["source"],
                    "url": a["url"],
                    "word_count": a["word_count"],
                    "summary": a.get("summary", "")
                } for a in deep_articles
            ],
            "commentary": left_commentary,
            "commentary_title": commentary_title
        }

    # 保存简报JSON
    briefing_dir = os.path.join(base_dir, "articles/daily")
    os.makedirs(briefing_dir, exist_ok=True)
    out_path = os.path.join(briefing_dir, f"{date_str}_briefing.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(briefing_data, f, ensure_ascii=False, indent=2)
    print(f"\n=== 简报已保存: {out_path} ({len(deep_articles)} 篇文章) ===")

if __name__ == "__main__":
    main()
