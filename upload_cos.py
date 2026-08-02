"""upload_cos.py - Upload RSS feed files and article HTML to Tencent Cloud COS."""
import os
from qcloud_cos import CosConfig, CosS3Client

def main():
    secret_id = os.environ["TENCENT_SECRET_ID"]
    secret_key = os.environ["TENCENT_SECRET_KEY"]
    bucket = os.environ["TENCENT_COS_BUCKET"]
    region = os.environ["TENCENT_COS_REGION"]

    config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
    client = CosS3Client(config)

    # 1. Upload all feed files
    files = ["feed2026.xml", "scmp_feed.xml", "deep.xml", "deep_v2.xml", "feed.xml", "feed.opml"]
    for filename in files:
        if not os.path.exists(filename):
            print("Skip {} (not found)".format(filename))
            continue
        with open(filename, "rb") as f:
            content = f.read()
        content_type = "application/rss+xml; charset=utf-8" if filename.endswith(".xml") else "text/x-opml; charset=utf-8"
        client.put_object(
            Bucket=bucket,
            Body=content,
            Key=filename,
            ContentType=content_type,
            CacheControl="max-age=300"
        )
        print("Uploaded {} ({} bytes)".format(filename, len(content)))

    # 2. Upload article HTML files (only today's to save time)
    # Determine today's date prefix
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    # Use TARGET_DATE if set, otherwise yesterday in Beijing time
    target_date = os.environ.get("TARGET_DATE", "")
    if not target_date:
        target_date = (now - timedelta(days=1)).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    date_prefix = target_date.replace("-", "")
    print("Uploading articles for {} (prefix={})".format(target_date, date_prefix))

    uploaded = 0
    for subdir in ["articles", "articles/scmp"]:
        if not os.path.isdir(subdir):
            continue
        for fname in os.listdir(subdir):
            if fname.endswith(".html") and fname.startswith(date_prefix):
                local_path = os.path.join(subdir, fname)
                cos_key = "{}/{}".format(subdir, fname)
                with open(local_path, "rb") as f:
                    content = f.read()
                client.put_object(
                    Bucket=bucket,
                    Body=content,
                    Key=cos_key,
                    ContentType="text/html; charset=utf-8",
                    CacheControl="max-age=86400"
                )
                uploaded += 1
                if uploaded % 10 == 0:
                    print("  Uploaded {} files...".format(uploaded))
    print("Uploaded {} article HTML files".format(uploaded))

    # 3. Upload briefing JSON
    briefing_path = "articles/daily/{}_briefing.json".format(target_date)
    if os.path.exists(briefing_path):
        with open(briefing_path, "rb") as f:
            content = f.read()
        client.put_object(
            Bucket=bucket,
            Body=content,
            Key=briefing_path,
            ContentType="application/json; charset=utf-8",
            CacheControl="max-age=86400"
        )
        print("Uploaded {}".format(briefing_path))

    cos_url = "https://{}.cos.{}.myqcloud.com/feed2026.xml".format(bucket, region)
    print("Feed URL: {}".format(cos_url))

if __name__ == "__main__":
    main()
