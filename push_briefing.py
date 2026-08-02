"""push_briefing.py - 读取已生成的简报JSON推送到微信（Server酱）
文章链接指向腾讯云COS（国内CDN快速访问）。
"""
import requests, json, os, re
from datetime import datetime, timedelta, timezone

SERVERCHAN_SENDKEY = os.environ.get("SERVERCHAN_SENDKEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = "1151785600-hue/caixin"
# COS链接（国内快速访问）
COS_BASE = "https://caixin-feed-1300461657.cos.ap-guangzhou.myqcloud.com/"
API_BASE = "https://api.github.com/repos/{}/git/trees/main?recursive=1".format(GITHUB_REPO)

def url_to_prefix(url):
    """Extract date+slug prefix from caixinglobal URL."""
    m = re.search(r'/(\d{4}-\d{2}-\d{2})/(.+?)(?:-\d+)?\.html', url)
    if m:
        date = m.group(1).replace('-', '')
        slug = m.group(2).replace('-', '_')[:70]
        return "{}_{}".format(date, slug)
    # SCMP URL: /article/XXXXXXX/slug
    m = re.search(r'/article/(\d+)/', url)
    if m:
        # Try to match by article ID in filename
        return m.group(1)
    return None

def get_file_list():
    """Get cached article filenames from GitHub API."""
    try:
        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = "token {}".format(GITHUB_TOKEN)
        r = requests.get(API_BASE, headers=headers, timeout=30)
        if r.status_code == 200:
            tree = r.json().get("tree", [])
            return [item["path"][9:] for item in tree
                    if item["path"].startswith("articles/")
                    and item["path"].endswith(".html")
                    and "/daily/" not in item["path"]
                    and not item["path"].endswith("_summary.json")]
        return []
    except Exception as e:
        print("  [GitHub API] error: {}".format(e))
        return []

def find_cached_url(url, file_list):
    """Find matching cached file and return COS URL."""
    prefix = url_to_prefix(url)
    if not prefix:
        return None
    # Try matching by date+slug prefix
    if len(prefix) == 8 or not prefix[8:].isdigit():
        # Date-based prefix (caixin)
        for path in file_list:
            fname = path.split("/")[-1]
            if fname.startswith(prefix):
                return COS_BASE + "articles/" + path
    else:
        # SCMP article ID match
        for path in file_list:
            fname = path.split("/")[-1]
            if prefix in fname:
                return COS_BASE + "articles/" + path
    return None

def push_to_wechat(title, content, max_retries=5):
    """Push to WeChat via Server酱 with retry logic."""
    if not SERVERCHAN_SENDKEY:
        print("  [Server酱] 未配置SendKey，跳过")
        return False
    import time
    for attempt in range(1, max_retries + 1):
        try:
            payload = {"title": title, "desp": content}
            resp = requests.post(
                "https://sctapi.ftqq.com/{}.send".format(SERVERCHAN_SENDKEY),
                data=payload,
                timeout=30
            )
            result = resp.json()
            code = result.get("code")
            print("  [Server酱] attempt {}/{} status={} code={} message={}".format(
                attempt, max_retries, resp.status_code, code, result.get('message', '')))
            if code == 0:
                print("  [Server酱] 推送成功")
                return True
            else:
                print("  [Server酱] 推送失败: {}".format(result))
        except Exception as e:
            print("  [Server酱] attempt {}/{} error: {}".format(attempt, max_retries, e))
        if attempt < max_retries:
            wait = 10 * attempt
            print("  [Server酱] {}秒后重试...".format(wait))
            time.sleep(wait)
    print("  [Server酱] {}次重试均失败".format(max_retries))
    return False

def main():
    base_dir = "."
    now = datetime.now(timezone.utc)
    bj_time = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    date_str = os.environ.get("BRIEFING_DATE", "")
    if not date_str:
        date_str = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    print("=== 推送简报 {} ===".format(bj_time))

    briefing_path = os.path.join(base_dir, "articles/daily", "{}_briefing.json".format(date_str))
    if not os.path.exists(briefing_path):
        print("  未找到简报文件: {}".format(briefing_path))
        yesterday = (now - timedelta(days=1)).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        briefing_path = os.path.join(base_dir, "articles/daily", "{}_briefing.json".format(yesterday))
        if not os.path.exists(briefing_path):
            print("  也未找到昨天简报: {}".format(briefing_path))
            return
        date_str = yesterday
        print("  回退使用昨天简报: {}".format(date_str))

    with open(briefing_path, "r", encoding="utf-8") as f:
        briefing_data = json.load(f)

    articles = briefing_data.get("articles", [])
    commentary = briefing_data.get("commentary", "")
    commentary_title = briefing_data.get("commentary_title", "")

    if not articles:
        print("  无新文章，发送空简报")
        push_to_wechat("Daily Briefing | {}".format(date_str),
                       "## Daily Briefing | {}\n\nNo new in-depth articles today.".format(date_str))
        return

    print("  找到 {} 篇文章".format(len(articles)))

    print("  正在获取缓存文件列表...")
    file_list = get_file_list()
    print("  缓存文件数: {}".format(len(file_list)))

    md_parts = ["## Daily Briefing | {}".format(date_str)]
    md_parts.append("{} in-depth articles\n".format(len(articles)))

    matched = 0
    for i, a in enumerate(articles, 1):
        source_tag = "SCMP" if a.get("source") == "scmp" else "Caixin"
        title = a.get("title", "Untitled")
        wc = a.get("word_count", "?")
        url = a.get("url", "")
        summary = a.get("summary", "")

        cached = find_cached_url(url, file_list)
        if cached:
            link = cached
            matched += 1
        else:
            link = url

        md_parts.append("**{}. [{}] {}**".format(i, source_tag, title))
        if cached:
            md_parts.append("  {} words | [Full Text]({})".format(wc, link))
        else:
            md_parts.append("  {} words | [Original]({})".format(wc, link))
        if summary:
            clean_summary = summary.strip()
            clean_summary = re.sub(r'^[\*\-\u2022]\s+', "- ", clean_summary, flags=re.MULTILINE)
            clean_summary = re.sub(r'\n{3,}', '\n\n', clean_summary)
            if len(clean_summary) > 400:
                clean_summary = clean_summary[:400] + "..."
            md_parts.append("")
            md_parts.append(clean_summary)
        md_parts.append("")
        md_parts.append("---")

    print("  链接匹配: {}/{} 篇使用COS链接".format(matched, len(articles)))

    if commentary:
        md_parts.append("")
        md_parts.append("### Political Economy Analysis")
        if commentary_title:
            md_parts.append("> {}".format(commentary_title))
        md_parts.append("")
        if len(commentary) > 5000:
            commentary = commentary[:5000] + "\n\n...(truncated)"
        md_parts.append(commentary)

    md_parts.append("")
    md_parts.append("---")
    md_parts.append("*Full archive: [COS](https://caixin-feed-1300461657.cos.ap-guangzhou.myqcloud.com/feed_daily.xml)*")

    full_md = "\n".join(md_parts)
    print("  推送内容长度: {} chars".format(len(full_md)))

    if len(full_md) > 32000:
        idx = full_md.find("---\n### Political Economy Analysis")
        if idx > 0:
            full_md = full_md[:idx] + "\n---\n*(Commentary truncated)*\n"
            print("  截断后: {} chars".format(len(full_md)))

    push_title = "Daily Briefing | {} | {} articles".format(date_str, len(articles))
    print("  正在推送: {}".format(push_title))
    push_to_wechat(push_title, full_md)
    print("\n=== 推送完成 ===")

if __name__ == "__main__":
    main()
