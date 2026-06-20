"""caixin_monitor.py - 财新网文章自动抓取
扫描财新网最新发布的文章，检测是否有分时免费正文，有则保存为HTML。
依赖: requests
"""
import requests
import re
import json
import os
import time
from datetime import datetime, timedelta


def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    return session


def find_today_articles(session):
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    dates = [today, yesterday]

    channels = ["www", "china", "economy", "finance", "companies"]
    all_urls = []

    for channel in channels:
        try:
            resp = session.get(f"https://{channel}.caixin.com/", timeout=15)
            if resp.status_code != 200:
                continue
            for date in dates:
                pattern = rf'href="((?:https?:)?//[^"]*caixin\.com/{re.escape(date)}/\d+\.html[^"]*)"'
                matches = re.findall(pattern, resp.text)
                for m in matches:
                    url = m if m.startswith("http") else "https:" + m
                    url = url.split("?")[0]
                    if url not in all_urls:
                        all_urls.append(url)
        except Exception:
            pass
        time.sleep(0.5)

    return all_urls


def extract_article(session, url):
    try:
        resp = session.get(url, timeout=12)
        if resp.status_code != 200:
            return None

        html = resp.text

        title_match = re.search(r"<title>(.*?)</title>", html)
        title = title_match.group(1).strip() if title_match else url.split("/")[-1]
        for suffix in ["_财新网", "_caixin", "_数据通", "_mini", "_财新文讯"]:
            title = title.replace(suffix, "")

        json_lds = re.findall(
            r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        body = ""
        for block in json_lds:
            try:
                data = json.loads(block)
                body = data.get("articleBody", "")
                if body:
                    break
            except (json.JSONDecodeError, AttributeError):
                continue

        if not body or len(body.split()) < 50:
            return None

        return {"title": title, "body": body, "word_count": len(body.split())}
    except Exception:
        return None


def save_as_html(article, url, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    safe_name = re.sub(r'[^\w\u4e00-\u9fff_-]', "_", article["title"])[:80]
    filepath = os.path.join(output_dir, f"{safe_name}.html")

    meta_text = f"财新网 | 抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    body_paras = article["body"].split("\n")

    lines = [
        '<!DOCTYPE html>',
        '<html lang="zh-CN">',
        '<head>',
        '<meta charset="UTF-8">',
        f'<title>{article["title"]}</title>',
        '<style>',
        'body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; max-width: 720px; margin: 0 auto; padding: 40px 20px; color: #222; line-height: 1.9; }',
        'h1 { font-size: 20pt; color: #1a1a2e; margin-bottom: 6px; line-height: 1.3; }',
        '.meta { font-size: 9pt; color: #999; margin-bottom: 30px; }',
        'p { margin-bottom: 12px; text-indent: 2em; }',
        '.source { font-size: 8.5pt; color: #aaa; margin-top: 40px; border-top: 1px solid #eee; padding-top: 12px; }',
        '</style>',
        '</head>',
        '<body>',
        f'<h1>{article["title"]}</h1>',
        f'<div class="meta">{meta_text}</div>',
    ]
    for para in body_paras:
        para = para.strip()
        if para:
            lines.append(f'<p>{para}</p>')

    lines.append(f'<div class="source">原文链接：<a href="{url}">{url}</a></div>')
    lines.append('</body>')
    lines.append('</html>')

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def main():
    output_dir = os.environ.get("OUTPUT_DIR", "articles")
    session = get_session()

    print(f"=== 财新网文章监控 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    urls = find_today_articles(session)
    print(f"发现 {len(urls)} 篇文章")

    saved = 0
    for url in urls:
        article = extract_article(session, url)
        if article:
            filepath = save_as_html(article, url, output_dir)
            saved += 1
            print(f"  [SAVED] {article['word_count']}w | {article['title'][:60]}")
            print(f"          -> {os.path.basename(filepath)}")

        time.sleep(0.8)

    print(f"\n本次运行保存 {saved} 篇文章")
    return saved


if __name__ == "__main__":
    main()
