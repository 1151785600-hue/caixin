"""caixin_monitor.py - 财新网 + CaixinGlobal 文章自动抓取 v6
双数据源:
  1. CaixinGlobal英文(caixinglobal.com): 提取所有c-content div中最长者，>300词视为全文
  2. 财新中文(caixin.com): HTML div提取正文预览(200-400字)，标注为preview
v6: 修正caixinglobal提取逻辑(取最长c-content div)，扩大日期范围到7天，放宽全文门槛到100词
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
        "Accept-Language": "en-US,en;q=0.9",
    })
    return session


# ============ CaixinGlobal 英文全文 ============

CAIXINGLOBAL_SECTIONS = [
    "china", "economy", "finance", "companies", "world", "opinion",
    "energy-environment", "tech", "culture", "property",
]

def find_caixinglobal_articles(session, days=7):
    """从caixinglobal.com各频道首页获取最近N天的文章链接"""
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

def extract_caixinglobal_article(session, url):
    """提取caixinglobal.com英文文章正文 - 取所有c-content div中最长者"""
    try:
        session.headers["Referer"] = url
        resp = session.get(url, timeout=12)
        if resp.status_code != 200:
            return None
        html = resp.text
        
        title_match = re.search(r"<title>(.*?)</title>", html)
        title = title_match.group(1).strip() if title_match else ""
        for suffix in [" | Caixin Global", "| Caixin Global", "- Caixin Global"]:
            title = title.replace(suffix, "").strip()
        
        # Extract ALL c-content divs, pick the longest one
        all_c_divs = re.findall(r'<div[^>]*class="[^"]*c-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        
        if not all_c_divs:
            return None
        
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
            return None
        
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
            "char_count": len(best_text),
            "category": "",
            "quality": quality,
            "language": "en",
        }
    except Exception as e:
        return None


# ============ 财新中文预览 ============

CAIXIN_CHANNELS = ["www", "china", "finance", "companies", "international", "opinion"]

def find_caixin_cn_articles(session, days=2):
    dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    all_urls = []
    for channel in CAIXIN_CHANNELS:
        for retry in range(2):
            try:
                url = f"https://{channel}.caixin.com/"
                session.headers["Referer"] = url
                resp = session.get(url, timeout=15)
                if resp.status_code != 200:
                    if retry == 0:
                        time.sleep(2)
                        continue
                    continue
                for date in dates:
                    pattern = rf'href="((?:https?:)?//[^"]*caixin\.com/{re.escape(date)}/\d+\.html)[^"]*"'
                    matches = re.findall(pattern, resp.text)
                    for m in matches:
                        full_url = m.split("?")[0].split("#")[0]
                        full_url = full_url if full_url.startswith("http") else "https:" + full_url
                        if full_url not in all_urls:
                            all_urls.append(full_url)
                break
            except Exception as e:
                print(f"  {channel}.caixin.com ERROR: {e}")
                if retry == 0:
                    time.sleep(2)
        time.sleep(0.5)
    return all_urls

def extract_caixin_cn_article(session, url):
    try:
        session.headers["Referer"] = url
        resp = session.get(url, timeout=12)
        if resp.status_code != 200:
            return None
        html = resp.text
        title_match = re.search(r"<title>(.*?)</title>", html)
        title = title_match.group(1).strip() if title_match else ""
        for suffix in ["_财新网", "_caixin", "_数据通", "_mini", "_财新文讯", "(含视频)"]:
            title = title.replace(suffix, "").strip()
        content_html = ""
        m = re.search(r'<div[^>]*id="Main_Content_Val"[^>]*>(.*?)</div>', html, re.DOTALL)
        if m:
            content_html = m.group(1)
        if not content_html.strip():
            m = re.search(r'<div[^>]*id="the_content"[^>]*>(.*?)</div>', html, re.DOTALL)
            if m:
                content_html = m.group(1)
        if not content_html.strip():
            m = re.search(r'<div[^>]*class="content"[^>]*>(.*?)</div>', html, re.DOTALL)
            if m:
                content_html = m.group(1)
        content_text = re.sub(r'<[^>]+>', '\n', content_html)
        content_text = re.sub(r'\n+', '\n', content_text).strip()
        paras = [p.strip() for p in content_text.split("\n") if p.strip()]
        content_text = "\n".join(paras)
        char_count = len(content_text)
        if char_count < 50:
            return None
        return {
            "title": title, "body": content_text,
            "word_count": char_count, "char_count": char_count,
            "category": "", "quality": "preview", "language": "zh",
        }
    except Exception as e:
        return None


# ============ 保存 ============

def save_as_html(article, url, output_dir, source):
    os.makedirs(output_dir, exist_ok=True)
    safe_name = re.sub(r'[^\w\u4e00-\u9fff_-]', "_", article["title"])[:80]
    filepath = os.path.join(output_dir, f"{safe_name}.html")
    lang = article.get("language", "en")
    font = '"Georgia", "Times New Roman", serif' if lang == "en" else '"Microsoft YaHei", "PingFang SC", sans-serif'
    if source == "caixinglobal":
        source_label = "Caixin Global"
        quality_label = article["quality"].upper()
        wc_label = f"{article['word_count']} words"
    else:
        source_label = "财新网"
        quality_label = "PREVIEW"
        wc_label = f"{article['word_count']} 字符"
    meta_text = f"{source_label} | {quality_label} | {wc_label} | {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    lines = [f'<!DOCTYPE html><html lang="{lang}"><head>',
             '<meta charset="UTF-8">', f'<title>{article["title"]}</title>',
             '<style>',
             f'body {{ font-family: {font}; max-width: 720px; margin: 0 auto; padding: 40px 20px; color: #222; line-height: 1.9; }}',
             'h1 { font-size: 18pt; color: #1a1a2e; margin-bottom: 6px; line-height: 1.3; }',
             '.meta { font-size: 9pt; color: #999; margin-bottom: 30px; }',
             'p { margin-bottom: 12px; text-indent: 2em; }',
             '.source { font-size: 8.5pt; color: #aaa; margin-top: 40px; border-top: 1px solid #eee; padding-top: 12px; }',
             '</style></head><body>',
             f'<h1>{article["title"]}</h1>',
             f'<div class="meta">{meta_text}</div>']
    for para in article["body"].split("\n"):
        if para.strip():
            lines.append(f"<p>{para.strip()}</p>")
    lines.append(f'<div class="source">原文链接：<a href="{url}">{url}</a></div>')
    lines.extend(['</body></html>'])
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filepath

def save_summary(data, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============ Main ============

def main():
    output_global = os.environ.get("OUTPUT_GLOBAL", "articles/global")
    output_cn = os.environ.get("OUTPUT_CN", "articles/cn_preview")
    session = get_session()
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"=== 财新双源监控 v6 {ts} ===")
    
    # Phase 1: CaixinGlobal
    print("\n[Phase 1] CaixinGlobal 英文文章扫描...")
    global_urls = find_caixinglobal_articles(session, days=7)
    print(f"  发现 {len(global_urls)} 篇英文文章")
    saved_global = 0
    global_info = []
    fulltext_count = 0
    partial_count = 0
    for i, url in enumerate(global_urls):
        article = extract_caixinglobal_article(session, url)
        if article:
            quality = article["quality"]
            if quality == "fulltext":
                fulltext_count += 1
            elif quality == "partial":
                partial_count += 1
            fp = save_as_html(article, url, output_global, "caixinglobal")
            saved_global += 1
            print(f"  [{i+1}/{len(global_urls)}] [{quality}] {article['word_count']:4d}w - {article['title'][:60]}")
            global_info.append({"url": url, "title": article["title"], "quality": quality, "word_count": article["word_count"]})
        else:
            print(f"  [{i+1}/{len(global_urls)}] [SKIP/404]")
        time.sleep(0.4)
    print(f"\n  英文: {saved_global}篇保存 ({fulltext_count}全文, {partial_count}部分, {saved_global-fulltext_count-partial_count}截断)")
    
    # Phase 2: CN preview (disabled by default)
    cn_enabled = os.environ.get("ENABLE_CN", "").lower() == "true"
    cn_info = []
    saved_cn = 0
    if cn_enabled:
        print("\n[Phase 2] 财新中文预览扫描...")
        cn_urls = find_caixin_cn_articles(session, days=2)
        print(f"  发现 {len(cn_urls)} 篇中文文章")
        for i, url in enumerate(cn_urls):
            article = extract_caixin_cn_article(session, url)
            if article:
                fp = save_as_html(article, url, output_cn, "caixin")
                saved_cn += 1
                print(f"  [{i+1}/{len(cn_urls)}] [preview] {article['word_count']}ch")
                cn_info.append({"url": url, "title": article["title"], "quality": "preview", "char_count": article["word_count"]})
            time.sleep(0.8)
        print(f"\n  中文预览: {saved_cn}篇保存")
    else:
        print("\n[Phase 2] 财新中文预览扫描 (已跳过)")
    
    total = saved_global + saved_cn
    print(f"\n=== 总计 {total} 篇 (英文{saved_global} + 中文{saved_cn}) ===")
    summary = {
        "timestamp": ts,
        "global": {"total": saved_global, "fulltext": fulltext_count, "partial": partial_count, "articles": global_info},
        "cn": {"total": saved_cn, "articles": cn_info},
    }
    save_summary(summary, "articles/_summary.json")
    return total

if __name__ == "__main__":
    main()
