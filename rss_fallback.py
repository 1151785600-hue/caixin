"""rss_fallback.py - Generate RSS feed directly from HTML files when briefing is empty."""
import os, re, glob, html as html_mod
from xml.etree.ElementTree import Element, SubElement, tostring
from datetime import datetime, timezone, timedelta

PAGES_BASE = "https://1151785600-hue.github.io/caixin"
THRESHOLD = 1000

def build_rss_from_html(articles_dir, output_path):
    """Scan HTML files in articles_dir and generate RSS feed with 1000+ word articles."""
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
            with open(fp, "r", encoding="utf-8") as fh:
                fc = fh.read()
            if len(fc) < 200:
                continue
            title_m = re.search(r"<title>(.*?)</title>", fc, re.DOTALL)
            title = title_m.group(1).strip() if title_m else os.path.basename(fp)
            paragraphs = re.findall(r"<p>(.*?)</p>", fc, re.DOTALL)
            body_paras = [p.strip() for p in paragraphs if p.strip()]
            body_text = " ".join(body_paras)
            wc = len(re.findall(r"[a-zA-Z]+", body_text))
            key = title.lower().strip()[:80]
            if key in seen:
                continue
            seen.add(key)
            if wc < THRESHOLD:
                continue
            meta_m = re.search(r"(\d{4}-\d{2}-\d{2})", fc[:500])
            date_str = meta_m.group(1) if meta_m else ""
            url_m = re.search(r'href="(https?://[^"]+)"', fc)
            source_url = url_m.group(1) if url_m else ""
            is_scmp = "/scmp/" in fp
            source = "SCMP" if is_scmp else "CAIXIN"
            body_html = "\n".join("<p>{}</p>".format(html_mod.escape(p)) for p in body_paras)
            gp_url = "{}/articles/scmp/{}".format(PAGES_BASE, os.path.basename(fp)) if is_scmp else "{}/articles/{}".format(PAGES_BASE, os.path.basename(fp))
            articles.append({"title": title, "source": source, "body_html": body_html,
                "body_text": body_text, "wc": wc, "date": date_str, "gp_url": gp_url, "source_url": source_url})
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
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(xml_str)
    print("RSS feed (HTML fallback): {} items written to {}".format(len(articles), output_path))
    return len(articles) > 0
