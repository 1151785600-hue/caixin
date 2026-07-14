"""Generate RSS 2.0 feed from daily briefing JSON files.

Each daily briefing becomes a <channel> update with <item> entries containing:
- Article title, link (GitHub Pages), summary (English), commentary (Chinese left-wing analysis)

Output: feed.xml served via GitHub Pages at
https://1151785600-hue.github.io/caixin/feed.xml

Designed to run in GitHub Actions after generate_briefing.py.
"""
import os, re, json, glob, html
from datetime import datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


PAGES_BASE = "https://1151785600-hue.github.io/caixin"


def escape_xml(text):
    """Escape text for XML CDATA or element content."""
    if not text:
        return ""
    return html.escape(str(text), quote=False)


def make_pages_url(source, original_url, articles_dir):
    """Convert original URL to GitHub Pages URL using local file lookup."""
    if source == "caixin":
        # Pattern: /YYYY-MM-DD/slug.html -> articles/YYYYMMDD_slug.html
        m = re.search(r"/(\d{4}-\d{2}-\d{2})/(.+?)\.html", original_url)
        if m:
            date_prefix = m.group(1).replace("-", "")
            slug = m.group(2)
            # Find actual file
            for f in glob.glob(os.path.join(articles_dir, f"{date_prefix}_*{slug[:20]}*.html")):
                return f"{PAGES_BASE}/articles/{os.path.basename(f)}"
    elif source == "scmp":
        # Pattern: /article/XXXXX -> articles/scmp/YYYYMMDD_scmp_XXXXX.html
        m = re.search(r"/(\d+)", original_url)
        if m:
            scmp_id = m.group(1)
            scmp_dir = os.path.join(articles_dir, "scmp")
            for f in glob.glob(os.path.join(scmp_dir, f"*{scmp_id}.html")):
                return f"{PAGES_BASE}/articles/scmp/{os.path.basename(f)}"
    # Fallback: return original URL
    return original_url


def markdown_to_html_simple(md):
    """Minimal Markdown to HTML conversion for commentary text."""
    if not md:
        return ""
    text = md
    # Headers
    for level in range(1, 7):
        text = re.sub(rf'^{"#" * level}\s+(.+)$', rf'<h{level}>\1</h{level}>', text, flags=re.MULTILINE)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # Blockquote (lines starting with >)
    text = re.sub(r'^>\s*(.+)$', r'<blockquote>\1</blockquote>', text, flags=re.MULTILINE)
    # Unordered list items
    text = re.sub(r'^\*\s+(.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    # Numbered list items
    text = re.sub(r'^\d+\.\s+(.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    # Paragraphs (double newline)
    text = re.sub(r'\n\n+', '</p><p>', text)
    # Single newlines to <br>
    text = text.replace('\n', '<br>')
    return f'<p>{text}</p>'


def build_rss(articles_dir, output_path):
    """Build RSS 2.0 XML from briefing JSON files."""
    rss = Element("rss", version="2.0",
                  xmlns_content="http://purl.org/rss/1.0/modules/content/")
    channel = SubElement(rss, "channel")

    # Channel metadata
    SubElement(channel, "title").text = "Caixin/SCMP Daily Briefing"
    SubElement(channel, "link").text = PAGES_BASE
    SubElement(channel, "description").text = "Daily deep report briefing with AI summaries and left-wing political economy commentary"
    SubElement(channel, "language").text = "en"
    bj_now = datetime.now(timezone(timedelta(hours=8)))
    SubElement(channel, "lastBuildDate").text = bj_now.strftime("%a, %d %b %Y %H:%M:%S +0800")
    SubElement(channel, "generator").text = "generate_rss.py"

    # Scan briefing JSON files (newest first)
    daily_dir = os.path.join(articles_dir, "daily")
    if not os.path.exists(daily_dir):
        print("No daily directory found")
        return

    briefing_files = sorted(glob.glob(os.path.join(daily_dir, "*_briefing.json")), reverse=True)

    total_items = 0
    for bf in briefing_files:
        try:
            with open(bf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            continue

        date_str = data.get("date", "")
        articles = data.get("articles", [])
        global_commentary = data.get("commentary", "")
        global_commentary_title = data.get("commentary_title", "")

        if not articles:
            continue

        # For each article, create an RSS item
        for a in articles:
            title = a.get("title", "Untitled")
            source = a.get("source", "unknown").upper()
            original_url = a.get("url", "")
            word_count = a.get("word_count", 0)
            summary = a.get("summary", "")

            # Build GitHub Pages URL
            gp_url = make_pages_url(source, original_url, articles_dir)

            item = SubElement(channel, "item")
            SubElement(item, "title").text = f"[{source}] {title}"

            SubElement(item, "link").text = gp_url

            # Build description: summary + global commentary
            desc_parts = []
            if source:
                desc_parts.append(f'<p><b>Source:</b> {source} | <b>Words:</b> {word_count}</p>')
            if summary:
                desc_parts.append(f'<p><b>AI Summary:</b></p><p>{escape_xml(summary)}</p>')
            if global_commentary:
                commentary_html = markdown_to_html_simple(global_commentary)
                desc_parts.append(f'<hr><p><b>Left-Wing Commentary{(" - " + escape_xml(global_commentary_title)) if global_commentary_title else ""}:</b></p>{commentary_html}')

            description = "\n".join(desc_parts)
            # Wrap in CDATA for safe HTML content
            desc_elem = SubElement(item, "description")
            desc_elem.text = f"<![CDATA[{description}]]>"

            # content:encoded for full HTML content
            content_elem = SubElement(item, "{http://purl.org/rss/1.0/modules/content/}encoded")
            content_elem.text = f"<![CDATA[{description}]]>"

            # Date
            pub_date = f"{date_str}T08:00:00+08:00" if date_str else bj_now.strftime("%a, %d %b %Y %H:%M:%S +0800")
            SubElement(item, "pubDate").text = pub_date

            # Category
            SubElement(item, "category").text = source

            total_items += 1

    # Pretty print
    rough = tostring(rss, encoding="unicode", xml_declaration=False)
    dom = minidom.parseString('<?xml version="1.0" encoding="UTF-8"?>' + rough)
    pretty = dom.toprettyxml(indent="  ")
    # Remove blank lines
    lines = [l for l in pretty.split("\n") if l.strip()]
    xml_str = "\n".join(lines) + "\n"

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)

    print(f"RSS feed: {total_items} items from {len(briefing_files)} briefings")
    print(f"Written to: {output_path} ({len(xml_str)} bytes)")
    print(f"URL: {PAGES_BASE}/{os.path.basename(output_path)}")


def main():
    articles_dir = os.environ.get("ARTICLES_DIR", "./articles")
    output_path = os.environ.get("RSS_OUTPUT", "./feed.xml")
    build_rss(articles_dir, output_path)


if __name__ == "__main__":
    main()
