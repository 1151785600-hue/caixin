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


def find_local_file(source, original_url, articles_dir):
    """Find the local HTML file path for an article."""
    if source == "caixin":
        m = re.search(r"/(\d{4}-\d{2}-\d{2})/(.+?)\.html", original_url)
        if m:
            date_prefix = m.group(1).replace("-", "")
            slug = m.group(2)
            for f in glob.glob(os.path.join(articles_dir, f"{date_prefix}_*{slug[:20]}*.html")):
                return f
    elif source == "scmp":
        m = re.search(r"/(\d+)", original_url)
        if m:
            scmp_id = m.group(1)
            scmp_dir = os.path.join(articles_dir, "scmp")
            for f in glob.glob(os.path.join(scmp_dir, f"*{scmp_id}.html")):
                return f
    return None


def make_pages_url(source, original_url, articles_dir):
    """Convert original URL to GitHub Pages URL using local file lookup."""
    local = find_local_file(source, original_url, articles_dir)
    if local:
        if source == "scmp":
            return f"{PAGES_BASE}/articles/scmp/{os.path.basename(local)}"
        else:
            return f"{PAGES_BASE}/articles/{os.path.basename(local)}"
    return original_url


def extract_article_body(html_file):
    """Extract the article body HTML from a saved HTML file.

    Returns the inner HTML of <article> or <div class='content'> or <div id='content'>
    or falls back to all <p> tags. Also prepends source attribution.
    """
    if not html_file or not os.path.exists(html_file):
        return ""
    try:
        with open(html_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Try <article> tag
        m = re.search(r'<article[^>]*>(.*?)</article>', content, re.DOTALL)
        if m and len(m.group(1)) > 200:
            body = m.group(1)
        else:
            # Try common content divs
            for pattern in [r'<div[^>]*class=["\']content["\'][^>]*>(.*?)</div>',
                           r'<div[^>]*id=["\']content["\'][^>]*>(.*?)</div>',
                           r'<div[^>]*class=["\']article-body["\'][^>]*>(.*?)</div>',
                           r'<div[^>]*class=["\']story-body["\'][^>]*>(.*?)</div>']:
                m = re.search(pattern, content, re.DOTALL)
                if m and len(m.group(1)) > 200:
                    body = m.group(1)
                    break
            else:
                # Fallback: extract all <p> tags (skip nav/header/footer)
                paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', content, re.DOTALL)
                # Skip very short paragraphs (likely nav/menu items)
                body_parts = []
                for p in paragraphs:
                    clean = re.sub(r'<[^>]+>', '', p).strip()
                    if len(clean) > 30:  # Only substantial paragraphs
                        body_parts.append(f"<p>{p}</p>")
                body = "\n".join(body_parts)

        if body:
            # Extract the source attribution link if present
            src_link = re.search(r'<a[^>]*href="(https?://[^"*]+)"[^>]*>\s*原文', content)
            if src_link:
                body = f'<p><a href="{src_link.group(1)}">Read original</a></p>\n' + body

        return body or ""
    except Exception as e:
        print(f"  Warning: could not extract body from {html_file}: {e}")
        return ""


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

            # content:encoded: embed full article HTML body
            local_html = find_local_file(source, original_url, articles_dir)
            full_body = extract_article_body(local_html)
            if full_body:
                full_content = full_body + "\n<hr>\n" + description
            else:
                full_content = description

            content_elem = SubElement(item, "{http://purl.org/rss/1.0/modules/content/}encoded")
            content_elem.text = f"<![CDATA[{full_content}]]>"

            # Date
            pub_date = f"{date_str}T08:00:00+08:00" if date_str else bj_now.strftime("%a, %d %b %Y %H:%M:%S +0800")
            SubElement(item, "pubDate").text = pub_date

            # Category
            SubElement(item, "category").text = source

            total_items += 1

    # Serialize with explicit UTF-8 encoding to avoid mojibake
    xml_str = tostring(rss, encoding="UTF-8", xml_declaration=True).decode("utf-8")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)

    print(f"RSS feed: {total_items} items from {len(briefing_files)} briefings")
    print(f"Written to: {output_path} ({len(xml_str)} bytes)")
    print(f"URL: {PAGES_BASE}/{os.path.basename(output_path)}")




def build_rss_from_html(articles_dir, output_path):
    """Fallback: when briefing JSON is empty, scan HTML files directly to build feed."""
    import os, re, glob, html as html_mod
    from xml.etree.ElementTree import Element, SubElement, tostring
    from datetime import datetime, timezone, timedelta

    PAGES_BASE = "https://1151785600-hue.github.io/caixin"
    THRESHOLD = 1000

    rss = Element("rss", version="2.0", xmlns_content="http://purl.org/rss/1.0/modules/content/")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "SCMP + Caixin Deep Reports"
    SubElement(channel, "link").text = PAGES_BASE
    SubElement(channel, "description").text = "Deep reports (1000+ words)"
    SubElement(channel, "language").text = "en"
    bj_now = datetime.now(timezone(timedelta(hours=8)))
    SubElement(channel, "lastBuildDate").text = bj_now.strftime("%a, %d %b %Y %H:%M:%S +0800")

    caixin_dir = articles_dir
    scmp_dir = os.path.join(articles_dir, "scmp")
    html_files = []
    if os.path.exists(caixin_dir):
        html_files.extend(glob.glob(os.path.join(caixin_dir, "*.html")))
    if os.path.exists(scmp_dir):
        html_files.extend(glob.glob(os.path.join(scmp_dir, "*.html")))

    articles = []
    seen = set()
    for fp in sorted(html_files, reverse=True):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content) < 200:
                continue
            title_m = re.search(r"<title>(.*?)</title>", content, re.DOTALL)
            title = title_m.group(1).strip() if title_m else os.path.basename(fp)
            paragraphs = re.findall(r"<p>(.*?)</p>", content, re.DOTALL)
            body_paras = [p.strip() for p in paragraphs if p.strip() and not p.strip().startswith("\u539f\u6587")]
            body_text = " ".join(body_paras)
            wc = len(re.findall(r"[a-zA-Z]+", body_text))
            key = title.lower().strip()[:80]
            if key in seen:
                continue
            seen.add(key)
            if wc < THRESHOLD:
                continue
            meta_m = re.search(r"(\d{4}-\d{2}-\d{2})", content[:500])
            date_str = meta_m.group(1) if meta_m else ""
            url_m = re.search(r'href="(https?://[^"]+)"', content.split("\u539f\u6587")[-1] if "\u539f\u6587" in content else content)
            source_url = url_m.group(1) if url_m else ""
            is_scmp = "/scmp/" in fp or "scmp" in content[:200].lower()
            source = "SCMP" if is_scmp else "CAIXIN"
            body_html = "\n".join("<p>{}</p>".format(html_mod.escape(p)) for p in body_paras)
            gp_url = "{}/articles/scmp/{}".format(PAGES_BASE, os.path.basename(fp)) if is_scmp else "{}/articles/{}".format(PAGES_BASE, os.path.basename(fp))
            articles.append({"title": title, "source": source, "body_html": body_html, "body_text": body_text, "wc": wc, "date": date_str, "gp_url": gp_url, "source_url": source_url})
        except Exception as e:
            print("  Warning: {}".format(e))

    articles.sort(key=lambda a: a["date"], reverse=True)

    for art in articles[:200]:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = "[{}] {}".format(art["source"], art["title"])
        SubElement(item, "link").text = art.get("source_url", art["gp_url"])
        SubElement(item, "guid", isPermaLink="false").text = art["gp_url"]
        pub = "{}T08:00:00+08:00".format(art["date"]) if art["date"] else bj_now.strftime("%a, %d %b %Y %H:%M:%S +0800")
        SubElement(item, "pubDate").text = pub
        desc_elem = SubElement(item, "description")
        desc_elem.text = "<![CDATA[<p>{}</p>]]>".format(html_mod.escape(art["body_text"][:500]))
        content_elem = SubElement(item, "{http://purl.org/rss/1.0/modules/content/}encoded")
        content_elem.text = "<![CDATA[{}]]>".format(art["body_html"])
        SubElement(item, "category").text = art["source"]

    xml_str = tostring(rss, encoding="UTF-8", xml_declaration=True).decode("utf-8")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
    print("RSS feed (HTML fallback): {} items written to {}".format(len(articles), output_path))

def main():
    articles_dir = os.environ.get("ARTICLES_DIR", "./articles")
    output_path = os.environ.get("RSS_OUTPUT", "./feed.xml")
    # Try briefing-based RSS first
    build_rss(articles_dir, output_path)
    # Fallback: if no items found from briefing, scan HTML files directly
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "<item>" not in content:
            print("WARNING: No items from briefing JSON, falling back to HTML scan...")
            build_rss_from_html(articles_dir, output_path)
    except:
        build_rss_from_html(articles_dir, output_path)


if __name__ == "__main__":
    main()
