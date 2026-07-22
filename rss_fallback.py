"""rss_fallback.py - Generate RSS feed directly from HTML files.
Accurate word count from body, proper date extraction, CDATA-safe output.
"""
import os, re, glob, html as html_mod
from datetime import datetime, timezone, timedelta

PAGES_BASE = "https://1151785600-hue.github.io/caixin"
THRESHOLD = 1000

def build_rss_from_html(articles_dir, output_path):
    """Scan HTML files and generate RSS feed with 1000+ word articles."""
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

            # Date: try meta div first, then filename, then full content
            date_str = ""
            meta_div = re.search(r'<div class="meta">(.*?)</div>', fc)
            if meta_div:
                dm = re.search(r"(\d{4}-\d{2}-\d{2})", meta_div.group(1))
                if dm:
                    date_str = dm.group(1)
            if not date_str:
                fn = os.path.basename(fp)
                fm = re.match(r"(\d{8})", fn)
                if fm:
                    d = fm.group(1)
                    date_str = "{}-{}-{}".format(d[:4], d[4:6], d[6:8])
            if not date_str:
                dm = re.search(r"(\d{4}-\d{2}-\d{2})", fc)
                if dm:
                    date_str = dm.group(1)

            url_m = re.search(r'href="(https?://[^"]+)"', fc)
            source_url = url_m.group(1) if url_m else ""
            is_scmp = "/scmp/" in fp or "scmp" in fc[:300].lower()
            source = "SCMP" if is_scmp else "CAIXIN"
            body_html = "\n".join("<p>{}</p>".format(p) for p in body_paras)
            gp_url = "{}/articles/scmp/{}".format(PAGES_BASE, os.path.basename(fp)) if is_scmp else "{}/articles/{}".format(PAGES_BASE, os.path.basename(fp))
            articles.append({"title": title, "source": source, "body_html": body_html,
                "body_text": body_text, "wc": wc, "date": date_str, "gp_url": gp_url, "source_url": source_url})
        except Exception as e:
            print("  Warning: {}".format(e))

    articles.sort(key=lambda a: a["date"], reverse=True)

    # Build XML manually (ElementTree mangles CDATA)
    bj_now = datetime.now(timezone(timedelta(hours=8)))
    lines = []
    lines.append('<?xml version="1.0" encoding="utf-8"?>')
    lines.append('<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">')
    lines.append('<channel>')
    lines.append('  <title>SCMP + Caixin Deep Reports</title>')
    lines.append('  <link>{}</link>'.format(PAGES_BASE))
    lines.append('  <description>Deep reports from SCMP and Caixin (1000+ words)</description>')
    lines.append('  <language>en</language>')
    lines.append('  <lastBuildDate>{}</lastBuildDate>'.format(bj_now.strftime("%a, %d %b %Y %H:%M:%S +0800")))
    lines.append('  <ttl>60</ttl>')

    for art in articles[:200]:
        if art["date"]:
                try:
                    dt = datetime.strptime(art["date"], "%Y-%m-%d")
                    pub = dt.strftime("%a, %d %b %Y 08:00:00 +0800")
                except:
                    pub = bj_now.strftime("%a, %d %b %Y %H:%M:%S +0800")
            else:
                pub = bj_now.strftime("%a, %d %b %Y %H:%M:%S +0800")
        lines.append('  <item>')
        lines.append('    <title>{}</title>'.format(html_mod.escape("[{}] {}".format(art["source"], art["title"]))))
        lines.append('    <link>{}</link>'.format(html_mod.escape(art.get("source_url", art["gp_url"]))))
        lines.append('    <guid isPermaLink="false">{}</guid>'.format(html_mod.escape(art["gp_url"])))
        lines.append('    <pubDate>{}</pubDate>'.format(pub))
        lines.append('    <description><![CDATA[<p>{}</p>]]></description>'.format(html_mod.escape(art["body_text"][:500])))
        lines.append('    <content:encoded><![CDATA[{}]]></content:encoded>'.format(art["body_html"]))
        lines.append('    <category>{}</category>'.format(art["source"]))
        lines.append('  </item>')

    lines.append('</channel>')
    lines.append('</rss>')
    xml_str = "\n".join(lines)

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(xml_str)
    print("RSS feed (HTML fallback): {} items written to {}".format(len(articles), output_path))
    return len(articles) > 0
