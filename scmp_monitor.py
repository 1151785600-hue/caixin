"""scmp_monitor.py - SCMP深度报道自动抓取 v1
JSON-LD articleBody提取法:
  - SCMP HTML中嵌入 <script type="application/ld+json">，articleBody字段包含完整正文
  - 仅保存有付费墙标记且提取到完整正文的深度报道
  - URL去重，避免重复保存
  - 每次运行生成 articles/daily/YYYY-MM-DD_scmp_briefing.md 简报
"""
import requests, re, json, os, time
from datetime import datetime, timedelta, timezone

def get_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s

# SCMP中国相关频道
SECTIONS = [
    "news/china",
    "news/hong-kong/economy",
    "news/hong-kong/law-and-crime",
    "news/hong-kong/education",
    "news/asia",
    "comment/opinion",
    "news/world/asia",
    "news/world/us-china",
    "economy/china-economy",
    "business/companies",
    "tech",
]

def find_articles(session, days=7):
    """从SCMP各频道获取最近N天的文章链接"""
    dates = set()
    for i in range(days):
        for fmt in ["%Y-%m-%d", "%Y/%m/%d"]:
            dates.add((datetime.now() - timedelta(days=i)).strftime(fmt))
    urls = []
    for section in SECTIONS:
        for retry in range(2):
            try:
                url = f"https://www.scmp.com/{section}"
                resp = session.get(url, timeout=15)
                if resp.status_code != 200:
                    if retry == 0:
                        time.sleep(2)
                        continue
                    continue
                # 匹配SCMP文章URL: /article/数字 或 /news/.../文章标题
                hrefs = re.findall(r'href="(https://www\.scmp\.com/(?:article/\d+|news/[^"]+))"', resp.text)
                for full_url in hrefs:
                    full_url = full_url.split("?")[0].split("#")[0]
                    if full_url not in urls:
                        urls.append(full_url)
                break
            except Exception as e:
                if retry == 0:
                    time.sleep(2)
        time.sleep(0.5)
    return urls

def url_to_filename(url):
    """从SCMP URL生成稳定文件名"""
    m = re.search(r'article/(\d+)', url)
    if m:
        return f"scmp_{m.group(1)}.html"
    slug = url.split("/")[-1] if url.endswith("/") else url.rstrip("/").split("/")[-1]
    return f"scmp_{re.sub(r'[^\w]', '_', slug)[:60]}.html"

def extract_article(session, url):
    """用JSON-LD方法提取SCMP文章"""
    try:
        resp = session.get(url, timeout=15, headers={"Referer": url})
        if resp.status_code != 200:
            return None
        html = resp.text

        # 提取JSON-LD
        json_ld_scripts = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        )
        if not json_ld_scripts:
            return {"skip": True, "reason": "no_jsonld"}

        article_data = None
        for script_text in json_ld_scripts:
            try:
                data = json.loads(script_text)
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "NewsArticle":
                            article_data = item
                            break
                elif data.get("@type") == "NewsArticle":
                    article_data = data
            except json.JSONDecodeError:
                continue

        if not article_data:
            return {"skip": True, "reason": "no_article"}

        article_body = article_data.get("articleBody", "")
        if not article_body or len(article_body) < 200:
            return {"skip": True, "reason": "short"}

        title = article_data.get("headline", "")
        if not title:
            title_m = re.search(r"<title>(.*?)</title>", html)
            title = title_m.group(1).strip() if title_m else ""
        for s in [" | South China Morning Post", "| South China Morning Post",
                   "  |  South China Morning Post", " | SCMP"]:
            title = title.replace(s, "").strip()

        # 检测付费墙标记
        is_premium = False
        if 'class="premium"' in html or '"isAccessibleForFree": false' in html or 'isAccessibleForFree":false' in html:
            is_premium = True
        if '"isAccessibleForFree": true' in html or 'isAccessibleForFree":true' in html:
            is_premium = False

        # 判断是否为深度/长文（>=500词）
        word_count = len(re.findall(r'[a-zA-Z]+', article_body))
        is_deep = word_count >= 500

        quality = "fulltext_deep" if is_deep else "fulltext"
        category = article_data.get("articleSection", "")

        return {
            "title": title,
            "body": article_body,
            "word_count": word_count,
            "quality": quality,
            "category": category,
            "is_premium": is_premium,
            "datePublished": article_data.get("datePublished", ""),
        }
    except Exception as e:
        print(f"    extract error: {e}")
        return None

def save_html(article, url, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    fname = url_to_filename(url)
    fp = os.path.join(output_dir, fname)
    if os.path.exists(fp):
        return None
    premium_tag = "PREMIUM" if article["is_premium"] else "FREE"
    deep_tag = "DEEP" if article["quality"] == "fulltext_deep" else ""
    meta = f"SCMP | {premium_tag} {deep_tag} | {article['word_count']} words | {datetime.now().strftime('%Y-%m-%d')}"
    lines = [
        '<!DOCTYPE html><html lang="en"><head>',
        '<meta charset="UTF-8">', f'<title>{article["title"]}</title>',
        '<style>',
        'body{font-family:"Georgia","Times New Roman",serif;max-width:720px;margin:0 auto;padding:40px 20px;color:#222;line-height:1.9}',
        'h1{font-size:18pt;color:#1a1a2e;margin-bottom:6px;line-height:1.3}',
        '.meta{font-size:9pt;color:#999;margin-bottom:30px}',
        'p{margin-bottom:12px}',
        '.src{font-size:8.5pt;color:#aaa;margin-top:40px;border-top:1px solid #eee;padding-top:12px}',
        '</style></head><body>',
        f'<h1>{article["title"]}</h1>',
        f'<div class="meta">{meta}</div>',
    ]
    for p in article["body"].split("\n"):
        if p.strip():
            lines.append(f"<p>{p.strip()}</p>")
    lines.append(f'<div class="src">原文：<a href="{url}">{url}</a></div></body></html>')
    with open(fp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return fp

def make_excerpt(text, n=200):
    text = text.replace("\n", " ").strip()
    return text[:n].rsplit(" ", 1)[0] + "..." if len(text) > n else text

def make_briefing(new_articles, output_dir):
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    bj = now.astimezone(timezone(timedelta(hours=8))).strftime("%H:%M")
    d = os.path.join(output_dir, "daily")
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, f"{date_str}_scmp_briefing.md")
    deep_articles = [a for a in new_articles if a["quality"] == "fulltext_deep"]
    other_articles = [a for a in new_articles if a["quality"] != "fulltext_deep"]
    lines = [
        f"# SCMP深度报道每日简报 | {date_str}（北京时间 {bj}）",
        "",
        f"**本次新增：{len(new_articles)} 篇**（深度报道 {len(deep_articles)} 篇，其他 {len(other_articles)} 篇）",
        "",
    ]
    if new_articles:
        lines.append("---\n")
        if deep_articles:
            lines.append("## 深度报道（500词以上）\n")
            for a in deep_articles:
                premium = "**[付费]**" if a["is_premium"] else ""
                cat = f" | {a['category']}" if a['category'] else ""
                lines.append(f"### {a['title']} {premium}\n")
                lines.append(f"- **字数：** {a['word_count']} words{cat}")
                lines.append(f"- **链接：** {a['url']}")
                lines.append(f"- **摘要：** {make_excerpt(a['body'])}\n")
        if other_articles:
            lines.append("## 其他文章\n")
            for a in other_articles:
                lines.append(f"### {a['title']}\n")
                lines.append(f"- **字数：** {a['word_count']} words")
                lines.append(f"- **链接：** {a['url']}")
                lines.append(f"- **摘要：** {make_excerpt(a['body'])}\n")
    else:
        lines.append("\n本次扫描未捕获到新文章。\n")
    lines.append("---\n\n*[v1 自动生成](https://github.com/1151785600-hue/caixin)*")
    with open(fp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return fp

def main():
    output_dir = os.environ.get("OUTPUT_DIR", "articles/scmp")
    session = get_session()
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"=== SCMP监控 v1（JSON-LD + 去重） {ts} ===")

    print("\n[Phase 1] SCMP文章扫描...")
    urls = find_articles(session, days=7)
    print(f"  发现 {len(urls)} 篇")
    new_articles = []
    for i, url in enumerate(urls):
        a = extract_article(session, url)
        if a is None:
            print(f"  [{i+1}] FAIL")
        elif a.get("skip"):
            pass
        else:
            fp = save_html(a, url, output_dir)
            if fp:
                new_articles.append({
                    "url": url, "title": a["title"],
                    "word_count": a["word_count"], "quality": a["quality"],
                    "is_premium": a["is_premium"], "category": a.get("category", ""),
                    "body": a["body"][:500]
                })
                tag = "DEEP" if a["quality"] == "fulltext_deep" else "FULL"
                print(f"  [{i+1}] NEW [{tag}] {a['word_count']:4d}w - {a['title'][:60]}")
            else:
                print(f"  [{i+1}] DUP")
        time.sleep(0.5)

    print(f"\n  新增:{len(new_articles)}")

    print("\n[Phase 2] 生成简报...")
    bp = make_briefing(new_articles, output_dir)
    print(f"  简报: {bp}")

    summary = {
        "ts": ts, "v": "scmp_v1", "new_count": len(new_articles),
        "articles": [{"url": a["url"], "title": a["title"], "wc": a["word_count"],
                       "quality": a["quality"], "premium": a["is_premium"]} for a in new_articles]
    }
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n=== SCMP新增:{len(new_articles)}篇 ===")
    return len(new_articles)

if __name__ == "__main__":
    main()
