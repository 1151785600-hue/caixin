"""push_briefing.py - 北京时间8点运行，读取已生成的简报JSON推送到微信（Server酱）
不调用任何AI接口，纯读取+推送，秒级完成。
推送标题列表+摘要+政治经济学评论。
文章链接指向GitHub仓库blob页面（public仓库可直接访问）。
"""
import requests, json, os
from datetime import datetime, timedelta, timezone

SERVERCHAN_SENDKEY = os.environ.get("SERVERCHAN_SENDKEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = "1151785600-hue/caixin"
BLOB_BASE = f"https://1151785600-hue.github.io/caixin/articles/"
API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}/git/trees/main?recursive=1"

def url_to_prefix(url):
    """Extract date+slug prefix from caixinglobal URL."""
    import re
    m = re.search(r'/(\d{4}-\d{2}-\d{2})/(.+?)(?:-\d+)?\.html', url)
    if m:
        date = m.group(1).replace('-', '')
        slug = m.group(2).replace('-', '_')[:70]
        return f"{date}_{slug}"
    return None

def get_file_list():
    """Get cached article filenames from GitHub API."""
    try:
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        r = requests.get(API_BASE, headers=headers, timeout=30)
        if r.status_code == 200:
            tree = r.json().get("tree", [])
            # strip 'articles/' prefix to avoid double path
            return [item["path"][9:] for item in tree
                    if item["path"].startswith("articles/")
                    and item["path"].endswith(".html")
                    and "/daily/" not in item["path"]
                    and not item["path"].endswith("_summary.json")
                    ]
        return []
    except Exception as e:
        print(f"  [GitHub API] error: {e}")
        return []

def find_cached_blob_url(url, file_list):
    """Find matching cached file and return GitHub blob page URL."""
    prefix = url_to_prefix(url)
    if not prefix:
        return url
    for path in file_list:
        fname = path.split("/")[-1]
        if fname.startswith(prefix):
            return BLOB_BASE + path
    return None

def push_to_wechat(title, content):
    if not SERVERCHAN_SENDKEY:
        print("  [Server酱] 未配置SendKey，跳过")
        return False
    try:
        payload = {"title": title, "desp": content}
        resp = requests.post(
            f"https://sctapi.ftqq.com/{SERVERCHAN_SENDKEY}.send",
            data=payload,
            timeout=15
        )
        result = resp.json()
        print(f"  [Server酱] status={resp.status_code} code={result.get('code')} message={result.get('message','')}")
        if result.get("code") == 0:
            print(f"  [Server酱] 推送成功")
            return True
        else:
            print(f"  [Server酱] 推送失败: {result}")
            return False
    except Exception as e:
        print(f"  [Server酱] error: {e}")
        return False

def main():
    base_dir = "."
    now = datetime.now(timezone.utc)
    bj_time = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    date_str = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    print(f"=== 推送简报 {bj_time} ===")

    # 读取简报JSON
    briefing_path = os.path.join(base_dir, "articles/daily", f"{date_str}_briefing.json")
    if not os.path.exists(briefing_path):
        print(f"  未找到简报文件: {briefing_path}")
        yesterday = (now - timedelta(days=1)).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        briefing_path = os.path.join(base_dir, "articles/daily", f"{yesterday}_briefing.json")
        if not os.path.exists(briefing_path):
            print(f"  也未找到昨天简报: {briefing_path}")
            return
        date_str = yesterday
        print(f"  回退使用昨天简报: {date_str}")

    with open(briefing_path, "r", encoding="utf-8") as f:
        briefing_data = json.load(f)

    articles = briefing_data.get("articles", [])
    commentary = briefing_data.get("commentary", "")
    commentary_title = briefing_data.get("commentary_title", "")

    if not articles:
        print("  无新文章，发送空简报")
        push_to_wechat(f"Daily Briefing | {date_str}", f"## Daily Briefing | {date_str}\n\nNo new in-depth articles today.")
        return

    print(f"  找到 {len(articles)} 篇文章")

    # 获取GitHub缓存文件列表（用于匹配链接）
    print(f"  正在获取缓存文件列表...")
    file_list = get_file_list()
    print(f"  缓存文件数: {len(file_list)}")

    # 组装Markdown (微信友好的HTML格式)
    md_parts = [f"## Daily Briefing | {date_str}"]
    md_parts.append(f"{len(articles)} in-depth articles\n")

    for i, a in enumerate(articles, 1):
        source_tag = "SCMP" if a.get("source") == "scmp" else "Caixin"
        title = a.get("title", "Untitled")
        wc = a.get("word_count", "?")
        url = a.get("url", "")
        summary = a.get("summary", "")

        # 尝试匹配GitHub缓存链接
        cached = find_cached_blob_url(url, file_list)
        link = cached if cached else url

        md_parts.append(f"**{i}. [{source_tag}] {title}**")
        md_parts.append(f"  {wc} words | [Cached Full Text]({link})" if cached else f"  {wc} words | [Original]({url})")
        if summary:
            # 清理摘要：统一为纯文本，去除列表符号和多余空白
            clean_summary = summary.strip()
            # 替换各种列表符号为换行+缩进
            import re
            clean_summary = re.sub(r'^[\*\-\u2022]\s+', "- ", clean_summary, flags=re.MULTILINE)
            # 去除连续空行
            clean_summary = re.sub(r'\n{3,}', '\n\n', clean_summary)
            if len(clean_summary) > 400:
                clean_summary = clean_summary[:400] + "..."
            md_parts.append("")
            md_parts.append(clean_summary)
        md_parts.append("")
        md_parts.append("---")

    # 评论部分
    if commentary:
        md_parts.append("")
        md_parts.append("### Political Economy Analysis")
        if commentary_title:
            md_parts.append(f"> {commentary_title}")
        md_parts.append("")
        # 截断到5000字符
        if len(commentary) > 5000:
            commentary = commentary[:5000] + "\n\n...(truncated)"
        md_parts.append(commentary)

    md_parts.append("")
    md_parts.append("---")
    md_parts.append(f"*Archive: [GitHub Pages](https://1151785600-hue.github.io/caixin/articles/)*")

    full_md = "\n".join(md_parts)
    print(f"  推送内容长度: {len(full_md)} chars")

    # 如果超限，截断评论
    if len(full_md) > 32000:
        idx = full_md.find("---\n### Political Economy Analysis")
        if idx > 0:
            full_md = full_md[:idx] + "\n---\n*(Commentary truncated)*\n"
            print(f"  截断后: {len(full_md)} chars")

    # 推送
    push_title = f"Daily Briefing | {date_str} | {len(articles)} articles"
    print(f"  正在推送: {push_title}")
    push_to_wechat(push_title, full_md)
    print(f"\n=== 推送完成 ===")

if __name__ == "__main__":
    main()
