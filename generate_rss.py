"""generate_rss.py - Generate RSS feed from HTML files.

This module uses rss_fallback.build_rss_from_html() to scan HTML files
directly, ensuring accurate word count filtering and proper CDATA support.
No longer depends on briefing JSON or ElementTree (which mangles CDATA).
"""
import os
import shutil

def main():
    articles_dir = os.environ.get("ARTICLES_DIR", "./articles")
    output_path = os.environ.get("RSS_OUTPUT", "./feed.xml")
    deep_path = os.environ.get("DEEP_OUTPUT", "./deep.xml")
    
    # Use rss_fallback as the only RSS generation method
    from rss_fallback import build_rss_from_html
    build_rss_from_html(articles_dir, output_path)
    
    # Copy feed.xml to deep.xml (OPML points to deep_v2.xml on Cloudflare,
    # but we also keep deep.xml in sync for compatibility)
    if os.path.exists(output_path):
        shutil.copy2(output_path, deep_path)
        print("Copied {} to {}".format(output_path, deep_path))
    
    # Also copy to deep_v2.xml for Cloudflare Pages
    deep_v2_path = os.environ.get("DEEP_V2_OUTPUT", "./deep_v2.xml")
    if os.path.exists(output_path):
        shutil.copy2(output_path, deep_v2_path)
        print("Copied {} to {}".format(output_path, deep_v2_path))

if __name__ == "__main__":
    main()
