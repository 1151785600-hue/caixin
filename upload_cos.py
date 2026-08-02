"""upload_cos.py - Upload RSS feed files and article HTML to Tencent Cloud COS."""
import os
import time
import json
import re
import requests as req
from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_exception import CosClientError, CosServiceError

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = "1151785600-hue/caixin"
RAW_BASE = "https://raw.githubusercontent.com/{}/main/".format(GITHUB_REPO)
API_TREE = "https://api.github.com/repos/{}/git/trees/main?recursive=1".format(GITHUB_REPO)

def upload_with_retry(client, bucket, key, body, content_type, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            client.put_object(
                Bucket=bucket,
                Body=body,
                Key=key,
                ContentType=content_type,
                CacheControl="max-age=86400"
            )
            return True
        except (CosClientError, CosServiceError) as e:
            print("  [COS] attempt {}/{} failed for {}: {}".format(attempt, max_retries, key, str(e)[:100]))
            if attempt < max_retries:
                time.sleep(5 * attempt)
    return False

def get_github_file_list():
    """Get all article HTML paths from GitHub git tree."""
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = "token {}".format(GITHUB_TOKEN)
    try:
        r = req.get(API_TREE, headers=headers, timeout=30)
        if r.status_code == 200:
            tree = r.json().get("tree", [])
            return [item["path"] for item in tree
                    if item["path"].startswith("articles/")
                    and item["path"].endswith(".html")
                    and "/daily/" not in item["path"]
                    and not item["path"].endswith("_summary.json")]
    except Exception as e:
        print("  [GitHub API] error: {}".format(e))
    return []

def download_from_github(github_path):
    """Download file content from GitHub raw."""
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = "token {}".format(GITHUB_TOKEN)
    url = RAW_BASE + github_path
    try:
        r = req.get(url, headers=headers, timeout=30)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        print("  [GitHub raw] error downloading {}: {}".format(github_path, e))
    return None

def main():
    secret_id = os.environ["TENCENT_SECRET_ID"]
    secret_key = os.environ["TENCENT_SECRET_KEY"]
    bucket = os.environ["TENCENT_COS_BUCKET"]
    region = os.environ["TENCENT_COS_REGION"]

    config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key, Timeout=120)
    client = CosS3Client(config)

    # 1. Upload feed files
    files = ["feed2026.xml", "scmp_feed.xml", "deep.xml", "deep_v2.xml", "feed.xml", "feed.opml"]
    for filename in files:
        if not os.path.exists(filename):
            continue
        with open(filename, "rb") as f:
            content = f.read()
        content_type = "application/rss+xml; charset=utf-8" if filename.endswith(".xml") else "text/x-opml; charset=utf-8"
        ok = upload_with_retry(client, bucket, filename, content, content_type)
        if ok:
            print("Uploaded {} ({} bytes)".format(filename, len(content)))

    # 2. Upload feed_daily.xml
    if os.path.exists("feed_daily.xml"):
        with open("feed_daily.xml", "rb") as f:
            content = f.read()
        ok = upload_with_retry(client, bucket, "feed_daily.xml", content, "application/rss+xml; charset=utf-8")
        if ok:
            print("Uploaded feed_daily.xml ({} bytes)".format(len(content)))

    # 3. Upload article HTML files referenced in briefing
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    target_date = os.environ.get("TARGET_DATE", "")
    if not target_date:
        target_date = (now - timedelta(days=1)).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

    briefing_path = "articles/daily/{}_briefing.json".format(target_date)
    files_to_upload = set()  # set of github_path strings

    # Read briefing to find which articles are referenced
    briefing_data = None
    if os.path.exists(briefing_path):
        with open(briefing_path, "r", encoding="utf-8") as f:
            briefing_data = json.load(f)

    if briefing_data:
        for a in briefing_data.get("articles", []):
            url = a.get("url", "")
            m = re.search(r'/article/(\d+)/', url)
            if m:
                article_id = m.group(1)
                # We'll match against GitHub file list later
                files_to_upload.add(("scmp_id", article_id))
            else:
                m = re.search(r'/(\d{4}-\d{2}-\d{2})/(.+?)(?:-\d+)?\.html', url)
                if m:
                    date_prefix = m.group(1).replace("-", "")
                    slug = m.group(2).replace("-", "_")[:70]
                    files_to_upload.add(("caixin_prefix", "{}_{}".format(date_prefix, slug)))

    # Get GitHub file list to find matching files
    print("Fetching GitHub file tree...")
    gh_files = get_github_file_list()
    print("GitHub article files: {}".format(len(gh_files)))

    # Match briefing articles to GitHub files
    matched_paths = set()
    for match_type, match_value in files_to_upload:
        for gh_path in gh_files:
            if match_type == "scmp_id":
                if match_value in gh_path:
                    matched_paths.add(gh_path)
                    break
            else:
                fname = gh_path.split("/")[-1]
                if fname.startswith(match_value):
                    matched_paths.add(gh_path)
                    break

    # Also add today's scraped files (local only)
    date_prefix = target_date.replace("-", "")
    for subdir in ["articles", "articles/scmp"]:
        if os.path.isdir(subdir):
            for fname in os.listdir(subdir):
                if fname.endswith(".html") and fname.startswith(date_prefix):
                    local_path = os.path.join(subdir, fname)
                    gh_path = "{}/{}".format(subdir, fname)
                    matched_paths.add(gh_path)

    print("Files to upload: {}".format(len(matched_paths)))

    uploaded = 0
    failed = 0
    for gh_path in sorted(matched_paths):
        # Try local file first
        if os.path.exists(gh_path):
            with open(gh_path, "rb") as f:
                content = f.read()
        else:
            # Download from GitHub raw (file was deleted locally by previous runs)
            print("  Downloading from GitHub: {}".format(gh_path))
            content = download_from_github(gh_path)
            if content is None:
                print("  SKIP: Cannot download {}".format(gh_path))
                failed += 1
                continue

        ok = upload_with_retry(client, bucket, gh_path, content, "text/html; charset=utf-8")
        if ok:
            uploaded += 1
        else:
            failed += 1
        if (uploaded + failed) % 5 == 0:
            print("  Progress: {} uploaded, {} failed".format(uploaded, failed))

    print("Article HTML: {} uploaded, {} failed".format(uploaded, failed))

    # 4. Upload briefing JSON
    if os.path.exists(briefing_path):
        with open(briefing_path, "rb") as f:
            content = f.read()
        ok = upload_with_retry(client, bucket, briefing_path, content, "application/json; charset=utf-8")
        if ok:
            print("Uploaded {}".format(briefing_path))

    print("Done. Feed URL: https://{}.cos.{}.myqcloud.com/feed_daily.xml".format(bucket, region))

if __name__ == "__main__":
    main()
