"""caixin_monitor.py - 财新付费文章自动抓取 v8.1
仅保存突破付费墙的完整文章:
  1. CaixinGlobal英文: 仅保存 quality=fulltext 的文章（分时免费窗口放行）
  2. 财新中文: 跳过（全部为截断预览，无法突破付费墙）
  3. 每次运行生成 articles/daily/YYYY-MM-DD_briefing.md 简报
"""
import requests
import re
import json
import os
import time
from datetime import datetime, timedelta, timezone

def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return session

CAIXINGLOBAL_SECTIONS = [
    "china", "economy", "finance", "companies", "world", "opinion",
    "energy-environment", "tech", "culture", "property",
]

def find_caixinglobal_articles(session, days=7):
    dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    all_urls = []
    for section in CAIXINGLOBAL_SECTIONS:
        for retry in range(2):
            try:
                url = f"https://www.caixinglobal.com/{section}/"
                session.headers["Referer"] = "https://www.caixinglobal.com/"
                resp = session.get(url, timeout=15)
                if resp.status_code != 200:
                    if retry == 0:
                        time.sleep(2)
                        continue
                    continue
                hrefs = re.findall(r'href="(https://www\.caixinglobal\.com/(\d{4}-\d{2}-\d{2})/[^"]+\.html)"', resp.text)
                for full_url, date in hrefs:
                    full_url = full_url.split("?")[0].split("#")[0]
                    if date in dates and full_url not in all_urls:
                        all_urls.append(full_url)
                break
            except Exception as e:
                print(f"  caixinglobal/{section} ERROR: {e}")
                if retry == 0:
                    time.sleep(2)
        time.sleep(0.5)
    return all_urls

def is_caixinglobal_paywalled(html):
    if '<!-- \u6536\u8d39\u5899 -->' in html:
        return True
    if 'cx-paywall' in html or 'paywall-content' in html:
        return True
    return False

def extract_caixinglobal_article(session, url):
    try:
        session.headers["Referer"] = url
        resp = session.get(url, timeout=12)
        if resp.status_code != 200:
            return None
        html = resp.text
        if not is_caixinglobal_paywalled(html):
            return {"skip": True, "reason": "free_article"}
        title_match = re.search(r"<title>(.*?)</title>", html)
        title = title_match.group(1).strip() if title_match else ""
        for suffix in [" | Caixin Global", "| Caixin Global", "- Caixin Global"]:
            title = title.replace(suffix, "").strip()
        all_c_divs = re.findall(r'<div[^>]*class="[^"]*c-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        if not all_c_divs:
            return {"skip": True, "reason": "no_content_div"}
        best_text = None
        best_wc = 0
        for div in all_c_divs:
            clean = re.sub(r'<script[^>]*>.*?</script>', '', div, flags=re.DOTALL)
            clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', '\n', clean)
            text = re.sub(r'AI generated[,.\s]*for reference only\.?', '', text, flags=re.IGNORECASE)
            text = re.sub(r'\n+', '\n', text).strip()
            wc = len(re.findall(r'[a-zA-Z]+', text))
            if wc > best_wc:
                best_wc = wc
                best_text = text
        if not best_text or best_wc < 30:
            return {"skip": True, "reason": "content_too_short"}
        paras = [p.strip() for p in best_text.split("\n") if p.strip()]
        best_text = "\n\n".join(paras)
        if best_wc >= 300:
            quality = "fulltext"
        elif best_wc >= 100:
            quality = "partial"
        else:
            quality = "truncated"
        return {
            "title": title,
            "body": best_text,
            "word_count": best_wc,
            "quality": quality,
            "language": "en",
            "is_paywalled": True,
        }
    except Exception:
        return None

def save_as_html(article, url, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    safe_name = re.sub(r'[^\w\u4e00-\u9fff_-]', "_", article["title"])[:80]
    date_prefix = datetime.now().strftime("%Y%m%d_%H%M")
    filepath = os.path.join(output_dir, f"{date_prefix}_{safe_name}.html")
    lines = [
        '<!DOCTYPE html><html lang="en"><head>',
        '<meta charset="UTF-8">', f'<title>{article["title"]}</title>',
        '<style>',
        'body { font-family: "Georgia", "Times New Roman", serif; max-width: 720px; margin: 0 auto; padding: 40px 20px; color: #222; line-height: 1.9; }',
        'h1 { font-size: 18pt; color: #1a1a2e; margin-bottom: 6px; line-height: 1.3; }',
        '.meta { font-size: 9pt; color: #999; margin-bottom: 30px; }',
        'p { margin-bottom: 12px; }',
        '.source { font-size: 8.5pt; color: #aaa; margin-top: 40px; border-top: 1px solid #eee; padding-top: 12px; }',
        '</style></head><body>',
        f'<h1>{article["title"]}</h1>',
        f'<div class="meta">Caixin Global | FULLTEXT | {article["word_count"]} words | {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>',
    ]
    for para in article["body"].split("\n"):
        if para.strip():
            lines.append(f"<p>{para.strip()}</p>")
    lines.append(f'<div class="source">原文链接：<a href="{url}">{url}</a></div>')
    lines.append('</body></html>')
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filepath

def make_excerpt(text, max_chars=200):
    text = text.replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."

def generate_briefing(fulltext_articles, output_dir):
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    bj_time = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    briefing_dir = os.path.join(output_dir, "daily")
    os.makedirs(briefing_dir, exist_ok=True)
    filepath = os.path.join(briefing_dir, f"{date_str}_briefing.md")
    lines = [
        f"# 财新付费文章每日简报",
        "",
        f"**日期：** {date_str}（北京时间 {bj_time} 生成）",
        "",
        f"**捕获全文文章：** {len(fulltext_articles)} 篇",
        "",
    ]
    if fulltext_articles:
        lines.append("---")
        lines.append("")
        lines.append("## 全文文章")
        lines.append("")
        for a in fulltext_articles:
            excerpt = make_excerpt(a["body"], 200)
            lines.append(f"### {a['title']}")
            lines.append("")
            lines.append(f"- **来源：** CaixinGlobal | **字数：** {a['word_count']} words")
            lines.append(f"- **链接：** {a['url']}")
            lines.append(f"- **摘要：** {excerpt}")
            lines.append("")
    else:
        lines.append("")
        lines.append("本次扫描未捕获到全文文章。")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*简报由财新监控脚本 v8.1 自动生成 | [查看仓库](https://github.com/1151785600-hue/caixin)*")
    content = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath

def main():
    output_dir = os.environ.get("OUTPUT_DIR", "articles")
    session = get_session()
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"=== 财新监控 v8.1（仅全文） {ts} ===")

    print("\n[Phase 1] CaixinGlobal 扫描...")
    global_urls = find_caixinglobal_articles(session, days=7)
    print(f"  发现 {len(global_urls)} 篇文章")
    saved = 0
    skipped_free = 0
    skipped_truncated = 0
    fulltext_info = []
    for i, url in enumerate(global_urls):
        article = extract_caixinglobal_article(session, url)
        if article is None:
            print(f"  [{i+1}/{len(global_urls)}] [FAIL]")
        elif isinstance(article, dict) and article.get("skip"):
            if article.get("reason") == "free_article":
                skipped_free += 1
            else:
                skipped_truncated += 1
            print(f"  [{i+1}/{len(global_urls)}] [SKIP]")
        elif article["quality"] == "fulltext":
            fp = save_as_html(article, url, output_dir)
            saved += 1
            print(f"  [{i+1}/{len(global_urls)}] [FULLTEXT] {article['word_count']:4d}w - {article['title'][:60]}")
            fulltext_info.append({"url": url, "title": article["title"], "word_count": article["word_count"], "body": article["body"][:500]})
        else:
            skipped_truncated += 1
            print(f"  [{i+1}/{len(global_urls)}] [{article['quality'].upper()}-SKIP] {article['word_count']}w")
        time.sleep(0.4)

    print(f"\n  全文:{saved} | 免费(跳过):{skipped_free} | 截断/部分(跳过):{skipped_truncated}")

    print("\n[Phase 2] 生成简报...")
    briefing_path = generate_briefing(fulltext_info, output_dir)
    print(f"  简报: {briefing_path}")

    print(f"\n=== 全文:{saved}篇 简报:1份 ===")
    summary = {
        "timestamp": ts,
        "version": "v8.1",
        "fulltext_count": saved,
        "skipped_free": skipped_free,
        "skipped_truncated": skipped_truncated,
        "articles": [{"url": a["url"], "title": a["title"], "word_count": a["word_count"]} for a in fulltext_info],
    }
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return saved

if __name__ == "__main__":
    main()
