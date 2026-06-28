"""push_briefing.py - 北京时间8点运行，读取已生成的简报JSON推送到微信（Server酱）
不调用任何AI接口，纯读取+推送，秒级完成。
Server酱desp字段限制约32000字符，因此只推送标题列表+政治经济学评论。
文章链接指向GitHub仓库中的缓存全文（通过API匹配文件名），而非官网。
"""
import requests, json, os, re
from datetime import datetime, timedelta, timezone

SERVERCHAN_SENDKEY = os.environ.get("SERVERCHAN_SENDKEY", "")
GITHUB_PAT = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = "1151785600-hue/caixin"

# GitHub blob URL base (htmlpreview or raw)
RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/articles/"

def url_to_prefix(url):
    """Extract date and slug prefix from caixinglobal URL."""
    m = re.search(r'/(\d{4}-\d{2}-\d{2})/(.+?)(?:-\d+)?\.html', url)
    if m:
        date = m.group(1).replace('-', '')
        slug = m.group(2).replace('-', '_')[:70]
        return f"{date}_{slug}"
    return None

def find_cached_url(url, file_list):
    """Find the matching cached file from article list, return GitHub blob URL."""
    prefix = url_to_prefix(url)
    if not prefix:
        return url  # fallback to original URL
    # Search for file starting with this prefix
    for fname in file_list:
        if fname.endswith('.html') and fname.startswith(prefix):
            return RAW_BASE + fname
    return None  # file not found in cache

def push_to_wechat(title, content):
    if not SERVERCHAN_SENDKEY:
        print("  [Server酱] 未配置SendKey，跳过")
        return False
    try:
        payload = {
            "title": title,
            "desp": content,
        }
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

def get_file_list():
    """Get list of cached article filenames from GitHub API."""
    try:
        headers = {}
        if GITHUB_PAT:
            headers["Authorization"] = f"token {GITHUB_PAT}"
        # Use tree API with recursive to get all files in articles/
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/git/trees/main?recursive=1",
            headers=headers, timeout=30
        )
        if r.status_code == 200:
            tree = r.json().get("tree", [])
            return [item["path"].split("/", 1)[1] for item in tree 
                    if item["path"].startswith("articles/") and item["type"] == "blob"
                    and item["path"].split("/", 1)[1] != "daily" 
                    and not item["path"].split("/", 1)[1].startswith("daily/")]
        else:
            print(f"  [GitHub API] error: {r.status_code}")
            return []
    except Exception as e:
        print(f"  [GitHub API] error: {e}")
        return []

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
        print("  简报中无文章，跳过推送")
        return

    print(f"  找到 {len(articles)} 篇文章")

    # 获取GitHub上缓存的文件列表
    print(f"  正在获取缓存文件列表...")
    file_list = get_file_list()
    print(f"  缓存文件数: {len(file_list)}")

    # 组装精简Markdown
    md_parts = [f"## Daily Briefing | {date_str}"]
    md_parts.append(f"**{len(articles)} in-depth articles**")
    md_parts.append("")

    # 按来源分组
    caixin_list = [a for a in articles if a.get("source") != "scmp"]
    scmp_list = [a for a in articles if a.get("source") == "scmp"]

    if caixin_list:
        md_parts.append(f"### Caixin Global ({len(caixin_list)})")
        for i, a in enumerate(caixin_list, 1):
            title = a.get("title", "Untitled")
            wc = a.get("word_count", "?")
            url = a.get("url", "")
            cached = find_cached_url(url, file_list)
            link = cached if cached else url
            tag = "" if cached else " [no cache]"
            md_parts.append(f"{i}. [{title}]({link}) ({wc} words){tag}")
        md_parts.append("")

    if scmp_list:
        md_parts.append(f"### SCMP ({len(scmp_list)})")
        for i, a in enumerate(scmp_list, 1):
            title = a.get("title", "Untitled")
            wc = a.get("word_count", "?")
            url = a.get("url", "")
            cached = find_cached_url(url, file_list)
            link = cached if cached else url
            tag = "" if cached else " [no cache]"
            md_parts.append(f"{i}. [{title}]({link}) ({wc} words){tag}")
        md_parts.append("")

    # 评论部分（截断到8000字符以内）
    if commentary:
        md_parts.append("---")
        md_parts.append("### Political Economy Analysis")
        if commentary_title:
            md_parts.append(f"*{commentary_title}*")
            md_parts.append("")
        if len(commentary) > 8000:
            commentary = commentary[:8000] + "\n\n...(truncated)"
        md_parts.append(commentary)

    md_parts.append("")
    md_parts.append("---")
    md_parts.append(f"*Full archive: [GitHub](https://github.com/{GITHUB_REPO}/tree/main/articles)*")

    full_md = "\n\n".join(md_parts)
    print(f"  推送内容长度: {len(full_md)} chars")

    # 推送
    push_title = f"Daily Briefing | {date_str} | {len(articles)} articles"
    print(f"  正在推送: {push_title}")
    push_to_wechat(push_title, full_md)
    print(f"\n=== 推送完成 ===")

if __name__ == "__main__":
    main()
