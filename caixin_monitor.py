"""caixin_monitor.py v8.2 - only save fulltext with URL dedup"""
import requests, re, json, os, time
from datetime import datetime, timedelta, timezone

def get_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"})
    return s

SECTIONS = ["china", "economy", "finance", "companies", "world", "opinion",
            "energy-environment", "tech", "culture", "property"]

def url_to_filename(url):
    m = re.search(r'/(\d{4}-\d{2}-\d{2})/(.+?)(?:-\d+)?\.html', url)
    if m:
        date = m.group(1).replace("-", "")
        slug = m.group(2).replace("-", "_")[:70]
        return f"{date}_{slug}.html"
    return re.sub(r'[^\w]', '_', url)[:80] + ".html"

def find_articles(session, days=7):
    dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    urls = []
    for section in SECTIONS:
        for retry in range(2):
            try:
                resp = session.get(f"https://www.caixinglobal.com/{section}/", timeout=15)
                if resp.status_code != 200:
                    if retry == 0: time.sleep(2); continue
                    continue
                for full_url, date in re.findall(r'href="(https://www\.caixinglobal\.com/(\d{4}-\d{2}-\d{2})/[^"]+\.html)"', resp.text):
                    full_url = full_url.split("?")[0].split("#")[0]
                    if date in dates and full_url not in urls:
                        urls.append(full_url)
                break
            except:
                if retry == 0: time.sleep(2)
        time.sleep(0.5)
    return urls

def extract_article(session, url):
    try:
        resp = session.get(url, timeout=12, headers={"Referer": url})
        if resp.status_code != 200: return None
        html = resp.text
        if '<!-- 收费墙 -->' not in html and 'cx-paywall' not in html:
            return {"skip": True, "reason": "free"}
        title = re.search(r"<title>(.*?)</title>", html)
        title = title.group(1).strip() if title else ""
        for s in [" | Caixin Global", "| Caixin Global", "- Caixin Global"]:
            title = title.replace(s, "").strip()
        divs = re.findall(r'<div[^>]*class="[^"]*c-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        if not divs: return {"skip": True, "reason": "no_div"}
        best, best_wc = None, 0
        for d in divs:
            t = re.sub(r'<script[^>]*>.*?</script>', '', d, flags=re.DOTALL)
            t = re.sub(r'<style[^>]*>.*?</style>', '', t, flags=re.DOTALL)
            t = re.sub(r'<[^>]+>', '\n', t)
            t = re.sub(r'AI generated[,.\s]*for reference only\.?', '', t, flags=re.IGNORECASE)
            t = re.sub(r'\n+', '\n', t).strip()
            wc = len(re.findall(r'[a-zA-Z]+', t))
            if wc > best_wc: best_wc = wc; best = t
        if not best or best_wc < 30: return {"skip": True, "reason": "short"}
        paras = [p.strip() for p in best.split("\n") if p.strip()]
        best = "\n\n".join(paras)
        quality = "fulltext" if best_wc >= 300 else ("partial" if best_wc >= 100 else "truncated")
        return {"title": title, "body": best, "word_count": best_wc, "quality": quality}
    except:
        return None

def save_html(article, url, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    fname = url_to_filename(url)
    fp = os.path.join(output_dir, fname)
    if os.path.exists(fp): return None
    lines = ['<!DOCTYPE html><html lang="en"><head>',
             '<meta charset="UTF-8">', f'<title>{article["title"]}</title>',
             '<style>body{font-family:"Georgia","Times New Roman",serif;max-width:720px;margin:0 auto;padding:40px 20px;color:#222;line-height:1.9}',
             'h1{font-size:18pt;color:#1a1a2e;margin-bottom:6px;line-height:1.3}',
             '.meta{font-size:9pt;color:#999;margin-bottom:30px}',
             'p{margin-bottom:12px}',
             '.src{font-size:8.5pt;color:#aaa;margin-top:40px;border-top:1px solid #eee;padding-top:12px}</style></head><body>',
             f'<h1>{article["title"]}</h1>',
             f'<div class="meta">Caixin Global | FULLTEXT | {article["word_count"]} words | {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>']
    for p in article["body"].split("\n"):
        if p.strip(): lines.append(f"<p>{p.strip()}</p>")
    lines.append(f'<div class="src">原文：<a href="{url}">{url}</a></div></body></html>')
    with open(fp, "w", encoding="utf-8") as f: f.write("\n".join(lines))
    return fp

def make_excerpt(text, n=200):
    text = text.replace("\n", " ").strip()
    return text[:n].rsplit(" ", 1)[0] + "..." if len(text) > n else text

def make_briefing(new_articles, output_dir):
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    bj = now.astimezone(timezone(timedelta(hours=8))).strftime("%H:%M")
    d = os.path.join(output_dir, "daily"); os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, f"{date_str}_briefing.md")
    lines = [f"# 财新付费文章简报 | {date_str}（北京时间 {bj}）", "",
            f"**本次新增全文：{len(new_articles)} 篇**", ""]
    if new_articles:
        lines.append("---\n\n## 新增全文文章\n")
        for a in new_articles:
            lines.append(f"### {a['title']}\n")
            lines.append(f"- **字数：** {a['word_count']} words")
            lines.append(f"- **链接：** {a['url']}")
            lines.append(f"- **摘要：** {make_excerpt(a['body'])}\n")
    else:
        lines.append("\n本次扫描未捕获到新的全文文章。\n")
    lines.append("---\n\n*[v8.2 自动生成](https://github.com/1151785600-hue/caixin)*")
    with open(fp, "w", encoding="utf-8") as f: f.write("\n".join(lines))
    return fp

def main():
    output_dir = os.environ.get("OUTPUT_DIR", "articles")
    session = get_session()
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"=== 财新监控 v8.2（仅全文+去重） {ts} ===")
    urls = find_articles(session, days=7)
    print(f"  {len(urls)} articles found")
    new_articles = []
    for i, url in enumerate(urls):
        a = extract_article(session, url)
        if a is None or a.get("skip"): continue
        elif a["quality"] == "fulltext":
            fp = save_html(a, url, output_dir)
            if fp:
                new_articles.append({"url": url, "title": a["title"], "word_count": a["word_count"], "body": a["body"][:500]})
                print(f"  [{i+1}] NEW {a['word_count']:4d}w - {a['title'][:60]}")
            else:
                print(f"  [{i+1}] DUP  {a['word_count']:4d}w")
        time.sleep(0.4)
    bp = make_briefing(new_articles, output_dir)
    print(f"  new:{len(new_articles)} briefing:{bp}")
    summary = {"ts": ts, "v": "8.2", "new_count": len(new_articles),
               "articles": [{"url": a["url"], "title": a["title"], "wc": a["word_count"]} for a in new_articles]}
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
