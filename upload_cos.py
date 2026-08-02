"""upload_cos.py - Upload RSS feed files and article HTML to Tencent Cloud COS."""
import os
import time
import json
import re
from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_exception import CosClientError, CosServiceError

def upload_with_retry(client, bucket, key, body, content_type, max_retries=3):
    """Upload a single file with retry logic."""
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

def main():
    secret_id = os.environ["TENCENT_SECRET_ID"]
    secret_key = os.environ["TENCENT_SECRET_KEY"]
    bucket = os.environ["TENCENT_COS_BUCKET"]
    region = os.environ["TENCENT_COS_REGION"]

    config = CosConfig(
        Region=region,
        SecretId=secret_id,
        SecretKey=secret_key,
        Timeout=120
    )
    client = CosS3Client(config)

    # 1. Upload feed files
    files = ["feed2026.xml", "scmp_feed.xml", "deep.xml", "deep_v2.xml", "feed.xml", "feed.opml"]
    for filename in files:
        if not os.path.exists(filename):
            print("Skip {} (not found)".format(filename))
            continue
        with open(filename, "rb") as f:
            content = f.read()
        content_type = "application/rss+xml; charset=utf-8" if filename.endswith(".xml") else "text/x-opml; charset=utf-8"
        ok = upload_with_retry(client, bucket, filename, content, content_type)
        if ok:
            print("Uploaded {} ({} bytes)".format(filename, len(content)))
        else:
            print("FAILED to upload {} after retries".format(filename))

    # 2. Upload article HTML files referenced in the briefing
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    target_date = os.environ.get("TARGET_DATE", "")
    if not target_date:
        target_date = (now - timedelta(days=1)).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

    briefing_path = "articles/daily/{}_briefing.json".format(target_date)
    files_to_upload = set()

    if os.path.exists(briefing_path):
        with open(briefing_path, "r", encoding="utf-8") as f:
            briefing = json.load(f)
        for a in briefing.get("articles", []):
            url = a.get("url", "")
            # Extract SCMP article ID
            m = re.search(r'/article/(\d+)/', url)
            if m:
                article_id = m.group(1)
                # Find matching local file
                for subdir in ["articles/scmp", "articles"]:
                    if os.path.isdir(subdir):
                        for fname in os.listdir(subdir):
                            if article_id in fname and fname.endswith(".html"):
                                local_path = os.path.join(subdir, fname)
                                cos_key = "{}/{}".format(subdir, fname)
                                files_to_upload.add((local_path, cos_key))
                                break
            else:
                # Caixin URL: extract date+slug
                m = re.search(r'/(\d{4}-\d{2}-\d{2})/(.+?)(?:-\d+)?\.html', url)
                if m:
                    date_prefix = m.group(1).replace("-", "")
                    slug = m.group(2).replace("-", "_")[:70]
                    prefix = "{}_{}".format(date_prefix, slug)
                    for subdir in ["articles", "articles/scmp"]:
                        if os.path.isdir(subdir):
                            for fname in os.listdir(subdir):
                                if fname.startswith(prefix) and fname.endswith(".html"):
                                    local_path = os.path.join(subdir, fname)
                                    cos_key = "{}/{}".format(subdir, fname)
                                    files_to_upload.add((local_path, cos_key))
                                    break

        # Also upload today's newly scraped files
        date_prefix = target_date.replace("-", "")
        for subdir in ["articles", "articles/scmp"]:
            if os.path.isdir(subdir):
                for fname in os.listdir(subdir):
                    if fname.endswith(".html") and fname.startswith(date_prefix):
                        local_path = os.path.join(subdir, fname)
                        cos_key = "{}/{}".format(subdir, fname)
                        files_to_upload.add((local_path, cos_key))

    print("Uploading {} article HTML files for {}".format(len(files_to_upload), target_date))

    uploaded = 0
    failed = 0
    for local_path, cos_key in sorted(files_to_upload):
        with open(local_path, "rb") as f:
            content = f.read()
        ok = upload_with_retry(client, bucket, cos_key, content, "text/html; charset=utf-8")
        if ok:
            uploaded += 1
        else:
            failed += 1
        if (uploaded + failed) % 5 == 0:
            print("  Progress: {} uploaded, {} failed".format(uploaded, failed))
    print("Article HTML: {} uploaded, {} failed".format(uploaded, failed))

    # 3. Upload briefing JSON
    if os.path.exists(briefing_path):
        with open(briefing_path, "rb") as f:
            content = f.read()
        ok = upload_with_retry(client, bucket, briefing_path, content, "application/json; charset=utf-8")
        if ok:
            print("Uploaded {}".format(briefing_path))

    # 4. Upload feed_daily.xml
    if os.path.exists("feed_daily.xml"):
        with open("feed_daily.xml", "rb") as f:
            content = f.read()
        ok = upload_with_retry(client, bucket, "feed_daily.xml", content, "application/rss+xml; charset=utf-8")
        if ok:
            print("Uploaded feed_daily.xml ({} bytes)".format(len(content)))

    print("Done. Feed URL: https://{}.cos.{}.myqcloud.com/feed_daily.xml".format(bucket, region))

if __name__ == "__main__":
    main()
