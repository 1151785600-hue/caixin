"""push_briefing.py - 北京时间8点运行，读取已生成的简报JSON推送到微信（Server酱）
不调用任何AI接口，纯读取+推送，秒级完成。
Server酱desp字段限制约32000字符，因此只推送标题列表+政治经济学评论。
"""
import requests, json, os
from datetime import datetime, timedelta, timezone

SERVERCHAN_SENDKEY = os.environ.get("SERVERCHAN_SENDKEY", "")

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

    # 组装精简Markdown（Server酱desp限制约32000字符）
    # 只放标题列表，不放摘要正文
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
            md_parts.append(f"{i}. [{title}]({url}) ({wc} words)")
        md_parts.append("")

    if scmp_list:
        md_parts.append(f"### SCMP ({len(scmp_list)})")
        for i, a in enumerate(scmp_list, 1):
            title = a.get("title", "Untitled")
            wc = a.get("word_count", "?")
            url = a.get("url", "")
            md_parts.append(f"{i}. [{title}]({url}) ({wc} words)")
        md_parts.append("")

    # 评论部分（截断到8000字符以内）
    if commentary:
        md_parts.append("---")
        md_parts.append("### Political Economy Analysis")
        if commentary_title:
            md_parts.append(f"*{commentary_title}*")
            md_parts.append("")
        # 截断评论避免超限
        if len(commentary) > 8000:
            commentary = commentary[:8000] + "\n\n...(truncated)"
        md_parts.append(commentary)

    md_parts.append("")
    md_parts.append("---")
    md_parts.append(f"*Full summaries & source links: [GitHub](https://github.com/1151785600-hue/caixin/tree/main/articles/daily)*")
    full_md = "\n\n".join(md_parts)

    print(f"  推送内容长度: {len(full_md)} chars")

    # 推送
    push_title = f"Daily Briefing | {date_str} | {len(articles)} articles"
    print(f"  正在推送: {push_title}")
    push_to_wechat(push_title, full_md)
    print(f"\n=== 推送完成 ===")

if __name__ == "__main__":
    main()
