"""Generate feed.opml - simplified version pointing to Cloudflare Pages."""
import os
from datetime import datetime, timezone, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring

def main():
    pages_base = os.environ.get("PAGES_BASE", "https://caixin-deep.pages.dev")
    output_path = os.environ.get("OPML_OUTPUT", "./feed.opml")

    opml = Element("opml", version="1.0")
    head = SubElement(opml, "head")
    SubElement(head, "title").text = "Deep Reports RSS"
    bj_now = datetime.now(timezone(timedelta(hours=8)))
    SubElement(head, "dateModified").text = bj_now.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    body = SubElement(opml, "body")
    SubElement(body, "outline",
        text="SCMP + Caixin Deep Reports (1000+ words)",
        title="SCMP + Caixin Deep Reports",
        type="rss",
        xmlUrl=pages_base + "/deep_v2.xml",
        htmlUrl=pages_base)

    xml_str = tostring(opml, encoding="unicode", xml_declaration=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
    print(f"OPML written to: {output_path} ({len(xml_str)} bytes)")

if __name__ == "__main__":
    main()
