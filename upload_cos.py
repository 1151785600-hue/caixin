"""upload_cos.py - Upload RSS feed files and article HTML to Tencent Cloud COS."""
import os
import time
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
                CacheControl="max-age=300"
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

    # Set longer timeout (120s) for slow US->China connection
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

    # 2. Upload article HTML files for target date
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    target_date = os.environ.get("TARGET_DATE", "")
    if not target_date:
        target_date = (now - timedelta(days=1)).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    date_prefix = target_date.replace("-", "")
    print("Uploading articles for {} (prefix={})".format(target_date, date_prefix))

    uploaded = 0
    failed = 0
    for subdir in ["articles", "articles/scmp"]:
        if not os.path.isdir(subdir):
            continue
        for fname in os.listdir(subdir):
            if fname.endswith(".html") and fname.startswith(date_prefix):
                local_path = os.path.join(subdir, fname)
                cos_key = "{}/{}".format(subdir, fname)
                with open(local_path, "rb") as f:
                    content = f.read()
                ok = upload_with_retry(client, bucket, cos_key, content, "text/html; charset=utf-8")
                if ok:
                    uploaded += 1
                else:
                    failed += 1
                if (uploaded + failed) % 10 == 0:
                    print("  Progress: {} uploaded, {} failed".format(uploaded, failed))
    print("Article HTML: {} uploaded, {} failed".format(uploaded, failed))

    # 3. Upload briefing JSON
    briefing_path = "articles/daily/{}_briefing.json".format(target_date)
    if os.path.exists(briefing_path):
        with open(briefing_path, "rb") as f:
            content = f.read()
        ok = upload_with_retry(client, bucket, briefing_path, content, "application/json; charset=utf-8")
        if ok:
            print("Uploaded {}".format(briefing_path))

    # 4. Rename feed_daily.xml -> feed_daily.xml (already named correctly in generate_rss.py)
    # Also upload feed_daily.xml if it exists
    if os.path.exists("feed_daily.xml"):
        with open("feed_daily.xml", "rb") as f:
            content = f.read()
        ok = upload_with_retry(client, bucket, "feed_daily.xml", content, "application/rss+xml; charset=utf-8")
        if ok:
            print("Uploaded feed_daily.xml ({} bytes)".format(len(content)))

    cos_url = "https://{}.cos.{}.myqcloud.com/feed_daily.xml".format(bucket, region)
    print("Feed URL: {}".format(cos_url))

if __name__ == "__main__":
    main()
