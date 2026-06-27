"""scmp_monitor.py v2 - SCMP深度报道自动抓取 + PushPlus微信推送
JSON-LD articleBody提取法，URL去重，每次运行后推送简报到微信
"""
import requests, re, json, os, time
from datetime import datetime, timedelta, timezone

PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")

def get_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"})
    return s

SECTIONS = [
    "news/china", "news/hong-kong/economy", "news/hong-kong/law-and-crime",
    "news/asia", "comment/opinion", "news/world/us-china",
    "economy/china-economy", "business/companies", "tech",
]

def find_articles(session, days=7):
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
                    if retry == 0: time.sleep(2); continue
                    continue
                hrefs = re.findall(r'href="(https://www\.scmp\.com/(?:article/\d+|news/[^"]+))"', resp.text)
                for full_url in hrefs:
                    full_url = full_url.split("?")[0].split("#")[0]
                    if full_url not in urls:
                        urls.append(full_url)
                break
            except:
                if retry == 0: time.sleep(2)
        time.sleep(0.5)
    return urls

def url_to_filename(url):
    m = re.search(r'article/(\d+)', url)
    if m:
        return f"scmp_{m.group(1)}.html"
    slug = url.rstrip("/").split("/")[-1]
    return f"scmp_{re.sub(r'[^\w]', '_', slug)[:60]}.html"

def extract_article(session, url):
    try:
        resp = session.get(url, timeout=15, headers={"Referer": url})
        if resp.status_code != 200: return None
        html = resp.text
        json_ld_scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
        if not json_ld_scripts:
            return {"skip": True, "reason": "no_jsonld"}
        article_data = None
        for script_text in json_ld_scripts:
            try:
                data = json.loads(script_text)
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "NewsArticle":
                            article_data = item; break
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
                   " | SCMP", " | south china morning post"]:
            title = title.replace(s, "").strip()
        is_premium = False
        if 'class="premium"' in html or '"isAccessibleForFree": false' in html or 'isAccessibleForFree":false' in html:
            is_premium = True
        if '"isAccessibleForFree": true' in html or 'isAccessibleForFree":true' in html:
            is_premium = False
        word_count = len(re.findall(r'[a-zA-Z]+', article_body))
        is_deep = word_count >= 500
        quality = "fulltext_deep" if is_deep else "fulltext"
        return {
            "title": title, "body": article_body, "word_count": word_count,
            "quality": quality, "is_premium": is_premium,
            "category": article_data.get("articleSection", ""),
            "datePublished": article_data.get("datePublished", ""),
        }
    except Exception as e:
        print(f"    extract error: {e}")
        return None

def save_html(article, url, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    fname = url_to_filename(url)
    fp = os.path.join(output_dir, fname)
    if os.path.exists(fp): return None
    premium_tag = "PREMIUM" if article["is_premium"] else "FREE"
    deep_tag = "DEEP" if article["quality"] == "fulltext_deep" else ""
    meta = f"SCMP | {premium_tag} {deep_tag} | {article['word_count']} words | {datetime.now().strftime('%Y-%m-%d')}"
    lines = [
        '<!DOCTYPE html><html lang="en"><head>',
        '<meta charset="UTF-8">', f'<title>{article["title"]}</title>',
        '<style>body{font-family:"Georgia","Times New Roman",serif;max-width:720px;margin:0 auto;padding:40px 20px;color:#222;line-height:1.9}',
        'h1{font-size:18pt;color:#1a1a2e;margin-bottom:6px;line-height:1.3}',
        '.meta{font-size:9pt;color:#999;margin-bottom:30px}',
        'p{margin-bottom:12px}',
        '.src{font-size:8.5pt;color:#aaa;margin-top:40px;border-top:1px solid #eee;padding-top:12px}</style></head><body>',
        f'<h1>{article["title"]}</h1>',
        f'<div class="meta">{meta}</div>',
    ]
    for p in article["body"].split("\n"):
        if p.strip(): lines.append(f"<p>{p.strip()}</p>")
    lines.append(f'<div class="src">原文：<a href="{url}">{url}</a></div></body></html>')
    with open(fp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return fp

def make_excerpt(text, n=200):
    text = text.replace("\n", " ").strip()
    return text[:n].rsplit(" ", 1)[0] + "..." if len(text) > n else text

def push_to_wechat(title, content):
    if not PUSHPLUS_TOKEN:
        print("  [PushPlus] 未配置token，跳过推送")
        return False
    try:
        payload = {"token": PUSHPLUS_TOKEN, "title": title, "content": content, "template": "markdown"}
        resp = requests.post("http://www.pushplus.plus/send", json=payload, timeout=15)
        result = resp.json()
        if result.get("code") == 200:
            print(f"  [PushPlus] 推送成功")
            return True
        else:
            print(f"  [PushPlus] 推送失败: {result.get('msg', 'unknown')}")
            return False
    except Exception as e:
        print(f"  [PushPlus] 推送异常: {e}")
        return False

def main():
    output_dir = os.environ.get("OUTPUT_DIR", "articles/scmp")
    session = get_session()
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"=== SCMP监控 v2（JSON-LD + 去重 + 微信推送） {ts} ===")
    urls = find_articles(session, days=7)
    print(f"  {len(urls)} articles found")
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
                    "url": url, "title": a["title"], "word_count": a["word_count"],
                    "quality": a["quality"], "is_premium": a["is_premium"],
                    "category": a.get("category", ""), "body": a["body"][:500]
                })
                tag = "DEEP" if a["quality"] == "fulltext_deep" else "FULL"
                print(f"  [{i+1}] NEW [{tag}] {a['word_count']:4d}w - {a['title'][:60]}")
            else:
                print(f"  [{i+1}] DUP")
        time.sleep(0.5)

    # 生成简报
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    bj = now.astimezone(timezone(timedelta(hours=8))).strftime("%H:%M")
    deep = [a for a in new_articles if a["quality"] == "fulltext_deep"]
    other = [a for a in new_articles if a["quality"] != "fulltext_deep"]
    md_lines = [f"**SCMP深度报道简报 | {date_str}（北京时间 {bj}）**\n",
                f"本次新增：**{len(new_articles)} 篇**（深度 {len(deep)}，其他 {len(other)}）\n"]
    if new_articles:
        md_lines.append("---\n")
        for a in new_articles:
            premium = " **[付费]**" if a["is_premium"] else ""
            md_lines.append(f"**{a['title']}**{premium}\n")
            md_lines.append(f"- 字数：{a['word_count']} words")
            md_lines.append(f"- [原文链接]({a['url']})")
            md_lines.append(f"- 摘要：{make_excerpt(a['body'])}\n")
    else:
        md_lines.append("本次扫描未捕获到新文章。\n")
    md_lines.append("---\n*[GitHub仓库](https://github.com/1151785600-hue/caixin)*")
    briefing_md = "\n".join(md_lines)

    # 保存简报
    d = os.path.join(output_dir, "daily"); os.makedirs(d, exist_ok=True)
    bp = os.path.join(d, f"{date_str}_scmp_briefing.md")
    with open(bp, "w", encoding="utf-8") as f: f.write(briefing_md)

    # 保存summary
    summary = {"ts": ts, "v": "scmp_v2", "new_count": len(new_articles),
               "articles": [{"url": a["url"], "title": a["title"], "wc": a["word_count"],
                             "quality": a["quality"], "premium": a["is_premium"]} for a in new_articles]}
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 推送到微信
    print(f"\n  新增:{len(new_articles)} 简报:{bp}")
    push_title = f"SCMP简报 | {date_str} | {len(new_articles)}篇"
    push_to_wechat(push_title, briefing_md)

if __name__ == "__main__":
    main()
