"""daily_briefing.py - 每日简报生成与推送
北京时间8点运行，处理前一天的抓取内容：
1. 过滤：只保留深度报道（SCMP>=500词; 财新>=300词）
2. 删除非深度文章文件
3. AI生成英文摘要（mimo-v2.5）
4. AI生成左翼评论（中文，七步法）
5. PushPlus推送到微信
"""
import requests, re, json, os, time, glob
from datetime import datetime, timedelta, timezone

PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_BASE_URL = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_MODEL = os.environ.get("MIMO_MODEL", "mimo-v2.5")

# ============ 深度报道筛选 ============

def is_deep_report(filepath):
    """从HTML文件判断是否为深度报道"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    # SCMP: fulltext_deep 已是深度
    if "fulltext_deep" in content:
        return True
    # CaixinGlobal: 检查meta中的word count
    m = re.search(r'(\d+)\s*words', content)
    if m and int(m.group(1)) >= 300:
        return True
    return False

def get_article_info(filepath):
    """从HTML文件提取标题、正文、URL、字数"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    title_m = re.search(r'<title>(.*?)</title>', content)
    title = title_m.group(1).strip() if title_m else os.path.basename(filepath)
    url_m = re.search(r'href="(https?://[^"]+)"', content.split("原文")[-1] if "原文" in content else content)
    url = url_m.group(1) if url_m else ""
    # 提取正文
    body_div = re.findall(r'<p>(.*?)</p>', content, re.DOTALL)
    body = "\n".join([re.sub(r'<[^>]+>', '', p).strip() for p in body_div if p.strip()])
    # 字数
    wc = len(re.findall(r'[a-zA-Z]+', body))
    return {"title": title, "body": body, "url": url, "word_count": wc, "filepath": filepath}

def filter_articles(base_dir):
    """扫描并过滤，返回深度报道列表，删除非深度文件"""
    caixin_dir = os.path.join(base_dir, "articles")
    scmp_dir = os.path.join(base_dir, "articles/scmp")
    deep_articles = []
    deleted_count = 0
    for search_dir, source in [(caixin_dir, "caixin"), (scmp_dir, "scmp")]:
        if not os.path.exists(search_dir):
            continue
        html_files = glob.glob(os.path.join(search_dir, "*.html"))
        for fp in html_files:
            if is_deep_report(fp):
                info = get_article_info(fp)
                info["source"] = source
                deep_articles.append(info)
            else:
                os.remove(fp)
                deleted_count += 1
                print(f"  [DEL] 非深度: {os.path.basename(fp)}")
    return deep_articles, deleted_count

# ============ AI 调用 ============

def call_mimo(prompt, max_tokens=2000):
    """调用 mimo-v2.5 API"""
    try:
        resp = requests.post(
            f"{MIMO_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {MIMO_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": MIMO_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.7,
            },
            timeout=60
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        else:
            print(f"  [MIMO] API error {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  [MIMO] error: {e}")
        return None

def generate_english_summary(article):
    """为单篇文章生成英文摘要"""
    body = article["body"][:3000]
    prompt = f"""Summarize the following article in 3-5 concise bullet points in English. Focus on key facts, data, and analysis. Do not add commentary.

Title: {article['title']}

Article:
{body}"""
    return call_mimo(prompt, max_tokens=500)

def generate_left_wing_commentary(article):
    """用左翼七步法生成中文评论"""
    body = article["body"][:4000]
    prompt = f"""你是一名左翼学者，精通马克思主义政治经济学、西方马克思主义、新左派理论。请用以下七步法对这篇新闻文章撰写一篇500-800字的中文评论：

1. 现象描述（简述核心事实）
2. 政治经济学定位（从生产关系、交换关系、分配关系切入）
3. 理论定位（选择最适合的左翼分析框架）
4. 深层分析（结构原因+历史原因）
5. 阶级/利益分析（谁受益、谁受损）
6. 意识形态批判（主流叙事如何掩盖实质）
7. 派系分歧与解放前景

要求：
- 引用至少一个经典作家（马克思/列宁/毛泽东/葛兰西/哈维等）的观点
- 呈现至少两个左翼派系的分歧
- 语言学术但不晦涩，面向受过良好教育的读者
- 不要用"综上所述"等套话结尾

标题: {article['title']}

正文:
{body}"""
    return call_mimo(prompt, max_tokens=2000)

# ============ PushPlus ============

def push_to_wechat(title, content):
    if not PUSHPLUS_TOKEN:
        print("  [PushPlus] 未配置token，跳过")
        return False
    try:
        payload = {"token": PUSHPLUS_TOKEN, "title": title, "content": content, "template": "html"}
        resp = requests.post("http://www.pushplus.plus/send", json=payload, timeout=15)
        result = resp.json()
        if result.get("code") == 200:
            print(f"  [PushPlus] 推送成功")
            return True
        else:
            print(f"  [PushPlus] 失败: {result.get('msg', 'unknown')}")
            return False
    except Exception as e:
        print(f"  [PushPlus] error: {e}")
        return False

# ============ 选择最佳左翼分析文章 ============

def select_best_for_analysis(articles):
    """选择最适合左翼分析的文章（优先涉及阶级/劳动/资本/权力/贫富等主题）"""
    keywords = ["worker", "labor", "capital", "class", "inequality", "poverty",
                "protest", "strike", "unemployment", "wage", "migrant",
                "corruption", "crackdown", "surveillance", "imperialism",
                "land", "evict", "housing", "debt", "austerity",
                "剥削", "阶级", "劳工", "罢工", "贫富", "腐败", "强拆",
                "labor", "wage", "AI", "automation", "tech", "platform",
                "energy", "carbon", "climate", "ecology",
                "sanction", "trade war", "tariff", "semiconductor"]
    scored = []
    for a in articles:
        title_lower = a["title"].lower()
        body_lower = a["body"][:1000].lower()
        score = 0
        for kw in keywords:
            if kw.lower() in title_lower:
                score += 3
            if kw.lower() in body_lower:
                score += 1
        # 偏好SCMP的analysis/in depth文章
        if "in depth" in title_lower or "analysis" in title_lower:
            score += 2
        if "cover story" in title_lower:
            score += 2
        scored.append((score, a))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else None

# ============ 主流程 ============

def main():
    base_dir = "."
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    bj_time = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    print(f"=== 每日简报 {bj_time} ===")

    # Phase 1: 过滤非深度报道
    print("\n[Phase 1] 筛选深度报道...")
    deep_articles, deleted_count = filter_articles(base_dir)
    print(f"  深度:{len(deep_articles)} 删除:{deleted_count}")

    if not deep_articles:
        print("  无深度报道，跳过推送")
        return

    # Phase 2: AI生成英文摘要
    print("\n[Phase 2] 生成英文摘要...")
    for a in deep_articles:
        print(f"  摘要: {a['title'][:50]}...")
        a["summary"] = generate_english_summary(a)
        if a["summary"]:
            print(f"    OK ({len(a['summary'])} chars)")
        else:
            a["summary"] = ""
        time.sleep(1)

    # Phase 3: 左翼评论（选最合适的一篇）
    print("\n[Phase 3] 生成左翼评论...")
    best = select_best_for_analysis(deep_articles)
    left_commentary = ""
    if best:
        print(f"  选中: {best['title'][:60]}")
        left_commentary = generate_left_wing_commentary(best)
        if left_commentary:
            print(f"    OK ({len(left_commentary)} chars)")
        else:
            left_commentary = "评论生成失败。"
    else:
        left_commentary = "未找到适合左翼分析的文章。"

    # Phase 4: 组装HTML推送内容
    print("\n[Phase 4] 组装推送内容...")
    html_parts = [f'<h2>Daily Briefing | {date_str}</h2>']
    html_parts.append(f'<p><b>Total: {len(deep_articles)} in-depth articles</b></p>')
    html_parts.append('<hr>')

    for a in deep_articles:
        source_tag = "SCMP" if a["source"] == "scmp" else "Caixin Global"
        html_parts.append(f'<h3>[{source_tag}] {a["title"]}</h3>')
        html_parts.append(f'<p>Words: {a["word_count"]} | <a href="{a["url"]}">Original</a></p>')
        if a.get("summary"):
            html_parts.append(f'<p><b>Summary:</b></p>')
            html_parts.append(f'<blockquote>{a["summary"]}</blockquote>')
        html_parts.append('<hr>')

    if left_commentary:
        html_parts.append('<h2>Left-Wing Analysis</h2>')
        if best:
            html_parts.append(f'<p><i>Analyzing: {best["title"]}</i></p>')
        html_parts.append(f'<div style="font-family:sans-serif;line-height:1.8">{left_commentary.replace(chr(10), "<br>")}</div>')
        html_parts.append('<hr>')

    html_parts.append(f'<p style="color:#999;font-size:10pt">Generated by caixin-monitor | <a href="https://github.com/1151785600-hue/caixin">GitHub</a></p>')
    full_html = "\n".join(html_parts)

    # 保存简报到本地
    briefing_dir = os.path.join(base_dir, "articles/daily")
    os.makedirs(briefing_dir, exist_ok=True)
    with open(os.path.join(briefing_dir, f"{date_str}_briefing.html"), "w", encoding="utf-8") as f:
        f.write(full_html)

    # Phase 5: PushPlus推送
    print("\n[Phase 5] 推送到微信...")
    push_title = f"Daily Briefing | {date_str} | {len(deep_articles)} articles"
    push_to_wechat(push_title, full_html)
    print(f"\n=== 简报完成 ===")

if __name__ == "__main__":
    main()
