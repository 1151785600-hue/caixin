"""caixin_monitor.py - 财新网文章自动抓取 v3
扫描财新网最新文章，从HTML Main_Content_Val div提取正文。
财新网正文是服务端渲染在HTML中的，不需要JSON-LD。
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
    channels = ["www", "china", "economy", "finance", "companies", "international", "opinion"]
    all_urls = []
    for channel in channels:
        try:
            url = f"https://{channel}.caixin.com/"
            resp = session.get(url, timeout=15)
            print(f"  {channel}.caixin.com -> {resp.status_code} ({len(resp.text)} bytes)")
            if resp.status_code != 200:
                continue
            for date in dates:
                pattern = rf'href="((?:https?:)?//[^"]*caixin\.com/{re.escape(date)}/\d+\.html)[^"]*"'
                matches = re.findall(pattern, resp.text)
                for m in matches:
                    full_url = m.split("?")[0].split("#")[0]
                    full_url = full_url if full_url.startswith("http") else "https:" + full_url
                    if full_url not in all_urls:
                        all_urls.append(full_url)
        except Exception as e:
            print(f"  {channel} ERROR: {e}")
        time.sleep(0.5)
    return all_urls

def extract_article(session, url):
    """从HTML中提取正文 - 财新正文在Main_Content_Val div中服务端渲染"""
    try:
        resp = session.get(url, timeout=12)
        if resp.status_code != 200:
            return None
        
        html = resp.text
        
        # 提取标题
        title_match = re.search(r"<title>(.*?)</title>", html)
        title = title_match.group(1).strip() if title_match else ""
        for suffix in ["_财新网", "_caixin", "_数据通", "_mini", "_财新文讯", "(含视频)"]:
            title = title.replace(suffix, "").strip()
        
        # 提取正文 - 尝试多个div选择器
        content_html = ""
        content_text = ""
        
        # 1. Main_Content_Val (主要正文区域)
        m = re.search(r'<div[^>]*id="Main_Content_Val"[^>]*>(.*?)</div>', html, re.DOTALL)
        if m:
            content_html = m.group(1)
        
        # 2. the_content (备选)
        if not content_html.strip():
            m = re.search(r'<div[^>]*id="the_content"[^>]*>(.*?)</div>', html, re.DOTALL)
            if m:
                content_html = m.group(1)
        
        # 3. class="content" (备选)
        if not content_html.strip():
            m = re.search(r'<div[^>]*class="content"[^>]*>(.*?)</div>', html, re.DOTALL)
            if m:
                content_html = m.group(1)
        
        # 提取纯文本
        content_text = re.sub(r'<[^>]+>', '\n', content_html)
        content_text = re.sub(r'\n+', '\n', content_text).strip()
        
        # 清除多余的空行
        paras = [p.strip() for p in content_text.split('\n') if p.strip()]
        content_text = '\n'.join(paras)
        
        wc = len(content_text)
        if wc < 50:
            print(f"    SHORT({wc}ch): {title[:50]}")
            return None
        
        print(f"    OK({wc}ch): {title[:50]}")
        return {
            "title": title,
            "body": content_text,
            "body_html": content_html,
            "word_count": wc
        }
    except Exception as e:
        print(f"    ERROR: {e}")
        return None

def save_as_html(article, url, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    safe_name = re.sub(r'[^\w\u4e00-\u9fff_-]', "_", article["title"])[:80]
    filepath = os.path.join(output_dir, f"{safe_name}.html")
    
    meta_text = f"财新网 | 抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    lines = [
        '<!DOCTYPE html>',
        '<html lang="zh-CN">',
        '<head>',
        '<meta charset="UTF-8">',
        f'<title>{article["title"]}</title>',
        '<style>',
        'body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; max-width: 720px; margin: 0 auto; padding: 40px 20px; color: #222; line-height: 1.9; }',
        'h1 { font-size: 18pt; color: #1a1a2e; margin-bottom: 6px; line-height: 1.3; }',
        '.meta { font-size: 9pt; color: #999; margin-bottom: 30px; }',
        'p { margin-bottom: 12px; text-indent: 2em; }',
        '.source { font-size: 8.5pt; color: #aaa; margin-top: 40px; border-top: 1px solid #eee; padding-top: 12px; }',
        '</style>',
        '</head>',
        '<body>',
        f'<h1>{article["title"]}</h1>',
        f'<div class="meta">{meta_text}</div>',
    ]
    for para in article["body"].split("\n"):
        para = para.strip()
        if para:
            lines.append(f'<p>{para}</p>')
    lines.append(f'<div class="source">原文链接：<a href="{url}">{url}</a></div>')
    lines.append('</body></html>')
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filepath

def save_article_list(info_list, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "_article_list.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(info_list, f, ensure_ascii=False, indent=2)

def main():
    output_dir = os.environ.get("OUTPUT_DIR", "articles")
    session = get_session()
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"=== 财新网文章监控 v3 {ts} ===")
    
    urls = find_today_articles(session)
    print(f"\n发现 {len(urls)} 篇文章 (去重后)")
    
    saved = 0
    info_list = []
    for i, url in enumerate(urls):
        print(f"[{i+1}/{len(urls)}] {url}")
        article = extract_article(session, url)
        info_list.append({"url": url, "saved": article is not None})
        if article:
            fp = save_as_html(article, url, output_dir)
            saved += 1
            print(f"  [SAVED] {article['word_count']}ch -> {os.path.basename(fp)}")
        time.sleep(0.8)
    
    save_article_list(info_list, output_dir)
    print(f"\n本次运行保存 {saved}/{len(urls)} 篇文章")
    return saved

if __name__ == "__main__":
    main()
