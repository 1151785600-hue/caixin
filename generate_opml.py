"""Generate feed.opml from articles in the repo.

Designed to run in GitHub Actions after generate_briefing.py.
Scans articles/caixin/, articles/scmp/, and articles/daily/ directories.
Writes feed.opml to the repo root for GitHub Pages to serve.
"""
import os, re, json, glob, base64
from datetime import datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


def get_title_from_html(filepath):
    """Extract title from HTML file's <h1> or <title> tag."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            head = f.read(2000)
        # Try <h1>
        m = re.search(r"<h1[^>]*>(.*?)</h1>", head, re.DOTALL)
        if m:
            return re.sub(r"<[^>]+>", "", m.group(1)).strip()
        # Try <title>
        m = re.search(r"<title>(.*?)</title>", head)
        if m:
            return m.group(1).strip()
    except:
        pass
    return None


def make_rss_item_xml_url(html_url):
    """Convert GitHub Pages HTML URL to RSS-style XML URL for OPML."""
    return html_url.replace(".html", ".xml")


def build_opml(briefing_articles, all_articles_dir, pages_base):
    """Build OPML XML tree."""
    opml = Element("opml", version="2.0")
    head = SubElement(opml, "head")
    SubElement(head, "title").text = "Caixin/SCMP Deep Report Feeds"
    bj_now = datetime.now(timezone(timedelta(hours=8)))
    SubElement(head, "dateModified").text = bj_now.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    SubElement(head, "ownerName").text = "Daily Briefing Bot"

    body = SubElement(opml, "body")

    # --- Outline 1: Daily Briefings ---
    briefing_outline = SubElement(body, "outline",
        text="Daily Briefings", title="Daily Briefings")

    # Scan all briefing JSON files
    daily_dir = os.path.join(all_articles_dir, "daily")
    if os.path.exists(daily_dir):
        briefing_files = sorted(glob.glob(os.path.join(daily_dir, "*_briefing.json")), reverse=True)
        for bf in briefing_files[:30]:  # Last 30 days
            date_str = os.path.basename(bf).replace("_briefing.json", "")
            try:
                with open(bf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                articles = data.get("articles", [])
                commentary = data.get("commentary", "")
            except:
                continue

            attrs = {
                "text": date_str,
                "title": date_str,
                "type": "rss",
                "xmlUrl": f"{pages_base}/articles/daily/{os.path.basename(bf).replace('.json', '.xml')}",
                "htmlUrl": f"{pages_base}/articles/daily/{os.path.basename(bf).replace('.json', '.html')}",
            }
            day_outline = SubElement(briefing_outline, "outline", **attrs)

            for a in articles:
                source = a.get("source", "unknown").upper()
                title = a.get("title", "Untitled")
                url = a.get("url", "")
                summary = a.get("summary", "")

                # Build GitHub Pages URL from source and original URL
                if source == "SCMP":
                    # SCMP articles stored at articles/scmp/
                    scmp_id = re.search(r"/(\d+)", url)
                    if scmp_id:
                        # Find the actual file in repo
                        scmp_dir = os.path.join(all_articles_dir, "scmp")
                        if os.path.exists(scmp_dir):
                            # Search for matching file
                            for sf in glob.glob(os.path.join(scmp_dir, f"*{scmp_id.group(1)}*.html")):
                                gp_url = f"{pages_base}/articles/scmp/{os.path.basename(sf)}"
                                url = gp_url
                                break
                elif source == "CAIXIN":
                    # Caixin articles stored at articles/
                    slug = re.search(r"/(\d{4}-\d{2}-\d{2})/(.+?)\.html", url)
                    if slug:
                        # Find matching file
                        prefix = slug.group(1).replace("-", "")
                        for cf in glob.glob(os.path.join(all_articles_dir, f"{prefix}_*.html")):
                            gp_url = f"{pages_base}/articles/{os.path.basename(cf)}"
                            url = gp_url
                            break

                item_attrs = {
                    "text": f"[{source}] {title}",
                    "title": title,
                    "type": "link",
                    "htmlUrl": url,
                }
                if summary:
                    item_attrs["description"] = summary[:200]
                SubElement(day_outline, "outline", **item_attrs)

    # --- Outline 2: All Caixin Articles by Date ---
    caixin_outline = SubElement(body, "outline",
        text="Caixin Articles", title="Caixin Articles")

    caixin_files = sorted(glob.glob(os.path.join(all_articles_dir, "*.html")))
    # Group by date
    by_date = {}
    for cf in caixin_files:
        fname = os.path.basename(cf)
        m = re.match(r"(\d{8})", fname)
        if m:
            date = m.group(1)
            if date not in by_date:
                by_date[date] = []
            title = get_title_from_html(cf) or fname.replace(".html", "")
            # Clean title: remove date prefix and time prefix
            title = re.sub(r"^\d{8}_?\d*_?", "", title).strip()
            title = re.sub(r"__+", " - ", title).strip()
            if title:
                by_date[date].append({
                    "title": title,
                    "url": f"{pages_base}/articles/{fname}",
                    "name": fname,
                })

    # Deduplicate per date by normalized title
    for date in sorted(by_date.keys(), reverse=True)[:30]:
        seen = set()
        unique = []
        for a in by_date[date]:
            norm = re.sub(r"\s+", " ", a["title"].lower().strip())
            if norm not in seen:
                seen.add(norm)
                unique.append(a)
        if not unique:
            continue

        date_display = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        day_outline = SubElement(caixin_outline, "outline",
            text=f"{date_display} ({len(unique)} articles)",
            title=date_display)

        for a in unique[:15]:
            SubElement(day_outline, "outline",
                text=a["title"],
                title=a["title"],
                type="link",
                htmlUrl=a["url"])

    # --- Outline 3: All SCMP Articles by Date ---
    scmp_outline = SubElement(body, "outline",
        text="SCMP Articles", title="SCMP Articles")

    scmp_dir = os.path.join(all_articles_dir, "scmp")
    if os.path.exists(scmp_dir):
        scmp_files = sorted(glob.glob(os.path.join(scmp_dir, "*.html")))
        by_date = {}
        for sf in scmp_files:
            fname = os.path.basename(sf)
            if not fname[0].isdigit():
                continue  # Skip old format without date prefix
            date = fname[:8]
            if date not in by_date:
                by_date[date] = []
            title = get_title_from_html(sf) or f"SCMP {fname}"
            by_date[date].append({
                "title": title,
                "url": f"{pages_base}/articles/scmp/{fname}",
            })

        for date in sorted(by_date.keys(), reverse=True)[:30]:
            date_display = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
            day_outline = SubElement(scmp_outline, "outline",
                text=f"{date_display} ({len(by_date[date])} articles)",
                title=date_display)
            for a in by_date[date][:15]:
                SubElement(day_outline, "outline",
                    text=a["title"],
                    title=a["title"],
                    type="link",
                    htmlUrl=a["url"])

    return opml


def prettify_xml(elem):
    """Pretty print XML with guaranteed UTF-8 encoding and XML declaration.

    The XML declaration (<?xml version='1.0' encoding='utf-8'?>) is critical
    because GitHub Pages serves .opml files with Content-Type: text/x-opml
    without a charset parameter, causing some clients to default to ISO-8859-1
    and produce mojibake for non-ASCII characters.
    """
    return tostring(elem, encoding="unicode", xml_declaration=True)


def main():
    articles_dir = os.environ.get("ARTICLES_DIR", "./articles")
    pages_base = os.environ.get("PAGES_BASE", "https://1151785600-hue.github.io/caixin")
    output_path = os.environ.get("OPML_OUTPUT", "./feed.opml")

    print(f"Scanning articles from: {articles_dir}")
    print(f"GitHub Pages base: {pages_base}")

    opml = build_opml([], articles_dir, pages_base)
    xml_str = prettify_xml(opml)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)

    print(f"OPML written to: {output_path} ({len(xml_str)} bytes)")
    print(f"URL: {pages_base}/feed.opml")


if __name__ == "__main__":
    main()
