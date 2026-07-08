"""scmp_monitor.py v4 - SCMP深度报道自动抓取
使用__NEXT_DATA__ JSON提取法（SCMP新版页面不再使用JSON-LD articleBody）。
URL去重，仅保存200+词的文章。
推送由 daily-briefing.py 统一处理。
"""
import requests, re, json, os, time
from datetime import datetime, timedelta, timezone

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
    urls = []
    for section in SECTIONS:
        for retry in range(2):
            try:
                resp = session.get(f"https://www.scmp.com/{section}", timeout=15)
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
    safe = re.sub(r"[^\w]", "_", slug)[:60]
    return f"scmp_{safe}.html"

def extract_from_next_data(html):
    """Extract article from __NEXT_DATA__ JSON (SCMP new layout)."""
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    try:
        article = data["props"]["pageProps"]["payload"]["json"]["data"]["article"]
    except (KeyError, TypeError):
        try:
            article = data["props"]["pageProps"]["data"]["article"]
        except (KeyError, TypeError):
            return None
    body_text = article.get("body", {}).get("text", "")
    if not body_text:
        return None
    return {
        "title": article.get("headline", ""),
        "body": body_text,
        "datePublished": article.get("publishedDate", ""),
        "section": article.get("articleSection", ""),
    }

def extract_from_json_ld(html):
    """Fallback: extract from JSON-LD (old layout)."""
    json_ld_scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for script_text in json_ld_scripts:
        try:
            data = json.loads(script_text)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "NewsArticle":
                    body = item.get("articleBody", "")
                    if body and len(body) >= 200:
                        return {
                            "title": item.get("headline", ""),
                            "body": body,
                            "datePublished": item.get("datePublished", ""),
                            "section": item.get("articleSection", ""),
                        }
        except json.JSONDecodeError:
            continue
    return None

def extract_article(session, url):
    try:
        resp = session.get(url, timeout=15, headers={"Referer": url})
        if resp.status_code != 200: return None
        html = resp.text
        article = extract_from_next_data(html)
        if not article or not article["body"]:
            article = extract_from_json_ld(html)
        if not article or not article["body"]:
            print(f"    SKIP: no_body | {url[:80]}")
            return {"skip": True, "reason": "no_body"}
        word_count = len(re.findall(r'[a-zA-Z]+', article["body"]))
        if word_count < 200:
            print(f"    SKIP: short ({word_count}w) | {url[:80]}")
            return {"skip": True, "reason": "short"}
        title = article["title"]
        title_m = re.search(r"<title>(.*?)</title>", html)
        if title_m and not title:
            title = title_m.group(1).strip()
        for s in [" | South China Morning Post", "| South China Morning Post", " | SCMP"]:
            title = title.replace(s, "").strip()
        is_premium = 'isAccessibleForFree": false' in html or "isAccessibleForFree': false" in html
        if 'isAccessibleForFree": true' in html or "isAccessibleForFree': true" in html:
            is_premium = False
        quality = "fulltext_deep" if word_count >= 500 else "fulltext"
        return {
            "title": title, "body": article["body"], "word_count": word_count,
            "quality": quality, "is_premium": is_premium,
            "datePublished": article.get("datePublished", ""),
            "section": article.get("section", ""),
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
    lines = ['<!DOCTYPE html><html lang="en"><head>',
             '<meta charset="UTF-8">', f'<title>{article["title"]}</title>',
             '<style>body{font-family:"Georgia","Times New Roman",serif;max-width:720px;margin:0 auto;padding:40px 20px;color:#222;line-height:1.9}',
             'h1{font-size:18pt;color:#1a1a2e;margin-bottom:6px;line-height:1.3}',
             '.meta{font-size:9pt;color:#999;margin-bottom:30px}',
             'p{margin-bottom:12px}',
             '.src{font-size:8.5pt;color:#aaa;margin-top:40px;border-top:1px solid #eee;padding-top:12px}</style></head><body>',
             f'<h1>{article["title"]}</h1>',
             f'<div class="meta">{meta}</div>']
    for p in article["body"].split("\n"):
        if p.strip(): lines.append(f"<p>{p.strip()}</p>")
    lines.append(f'<div class="src">原文：<a href="{url}">{url}</a></div></body></html>')
    with open(fp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return fp

def main():
    output_dir = os.environ.get("OUTPUT_DIR", "articles/scmp")
    session = get_session()
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"=== SCMP监控 v4 {ts} ===")
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
                new_articles.append({"url": url, "title": a["title"], "word_count": a["word_count"],
                    "quality": a["quality"], "is_premium": a["is_premium"]})
                tag = "DEEP" if a["quality"] == "fulltext_deep" else "FULL"
                print(f"  [{i+1}] NEW [{tag}] {a['word_count']:4d}w - {a['title'][:60]}")
            else:
                print(f"  [{i+1}] DUP")
        time.sleep(0.5)
    print(f"\n  新增:{len(new_articles)}")
    summary = {"ts": ts, "v": "scmp_v4", "new_count": len(new_articles), "articles": new_articles}
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
