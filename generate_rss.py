"""generate_rss.py - Generate RSS feed from HTML files.

Uses rss_fallback.build_rss_from_html() to scan HTML files directly.
If rss_fallback fails, falls back to build_rss (briefing-based).
"""
import os
import sys
import shutil

def main():
    articles_dir = os.environ.get("ARTICLES_DIR", "./articles")
    output_path = os.environ.get("RSS_OUTPUT", "./feed.xml")

    # Primary: use rss_fallback (direct HTML scan, correct XML format)
    try:
        from rss_fallback import build_rss_from_html
        build_rss_from_html(articles_dir, output_path)
        print("RSS generated via rss_fallback")
    except Exception as e:
        print("WARNING: rss_fallback failed: {}".format(e))
        print("Falling back to build_rss (briefing-based)...")
        try:
            build_rss(articles_dir, output_path)
        except Exception as e2:
            print("ERROR: build_rss also failed: {}".format(e2))
            return

    # Copy feed.xml to all output files
    targets = [
        os.environ.get("DEEP_OUTPUT", "./deep.xml"),
        os.environ.get("DEEP_V2_OUTPUT", "./deep_v2.xml"),
        os.environ.get("SCMP_FEED_OUTPUT", "./scmp_feed.xml"),
        os.environ.get("FEED2026_OUTPUT", "./feed2026.xml"),
    ]
    for target in targets:
        if os.path.exists(output_path):
            shutil.copy2(output_path, target)
            print("Copied to {}".format(target))

if __name__ == "__main__":
    main()
