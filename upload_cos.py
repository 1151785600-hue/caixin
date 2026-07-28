"""upload_cos.py - Upload RSS feed files to Tencent Cloud COS."""
import os
from qcloud_cos import CosConfig, CosS3Client

def main():
    secret_id = os.environ["TENCENT_SECRET_ID"]
    secret_key = os.environ["TENCENT_SECRET_KEY"]
    bucket = os.environ["TENCENT_COS_BUCKET"]
    region = os.environ["TENCENT_COS_REGION"]

    config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
    client = CosS3Client(config)

    # Upload all feed files
    files = ["feed2026.xml", "scmp_feed.xml", "deep.xml", "deep_v2.xml", "feed.xml", "feed.opml"]
    for filename in files:
        if not os.path.exists(filename):
            print("Skip {} (not found)".format(filename))
            continue
        with open(filename, "rb") as f:
            content = f.read()
        content_type = "application/xml; charset=utf-8" if filename.endswith(".xml") else "text/x-opml; charset=utf-8"
        client.put_object(
            Bucket=bucket,
            Body=content,
            Key=filename,
            ContentType=content_type,
            CacheControl="max-age=300"
        )
        print("Uploaded {} ({} bytes)".format(filename, len(content)))

    cos_url = "https://{}.cos.{}.myqcloud.com/feed2026.xml".format(bucket, region)
    print("Feed URL: {}".format(cos_url))

if __name__ == "__main__":
    main()
