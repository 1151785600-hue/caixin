"""push_briefing.py - 北京时间8点运行，读取已生成的简报JSON推送到微信（Server酱）
不调用任何AI接口，纯读取+推送，秒级完成。
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
            f"https://sct.ftqq.com/{SERVERCHAN_SENDKEY}.send",
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
        p
