"""Debug: print __NEXT_DATA__ JSON structure from SCMP section pages."""
import requests, re, json, os

def get_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    })
    return s

def print_structure(data, prefix="", max_depth=4, max_items=3):
    """Recursively print JSON structure."""
    if max_depth <= 0:
        print(f"{prefix}[MAX DEPTH]")
        return
    
    if isinstance(data, dict):
        for k, v in list(data.items())[:max_items]:
            if isinstance(v, dict):
                print(f"{prefix}{k}: (dict, {len(v)} keys)")
                print_structure(v, prefix + "  ", max_depth - 1, max_items)
            elif isinstance(v, list):
                print(f"{prefix}{k}: (list, {len(v)} items)")
                if v and isinstance(v[0], dict):
                    print_structure(v[0], prefix + "  [0].", max_depth - 1, max_items)
            elif isinstance(v, str):
                print(f"{prefix}{k}: \"{v[:60]}\"")
            else:
                print(f"{prefix}{k}: {type(v).__name__} = {str(v)[:60]}")
        if len(data) > max_items:
            print(f"{prefix}... ({len(data) - max_items} more keys)")
    elif isinstance(data, list):
        for i, item in enumerate(data[:max_items]):
            if isinstance(item, dict):
                print(f"{prefix}[{i}]: (dict, {len(item)} keys)")
                print_structure(item, prefix + "  ", max_depth - 1, max_items)
            else:
                print(f"{prefix}[{i}]: {type(item).__name__}")

def find_all_urls(data, path=""):
    """Find all strings that look like SCMP article URLs."""
    found = []
    if isinstance(data, dict):
        for k, v in data.items():
            found.extend(find_all_urls(v, f"{path}.{k}"))
            if isinstance(v, str) and "/article/" in v:
                found.append((path + "." + k, v))
    elif isinstance(data, list):
        for i, v in enumerate(data[:20]):
            found.extend(find_all_urls(v, f"{path}[{i}]"))
    return found

def main():
    session = get_session()
    
    # Test one section
    section = "news/china"
    print(f"=== Fetching https://www.scmp.com/{section} ===")
    resp = session.get(f"https://www.scmp.com/{section}", timeout=15)
    print(f"Status: {resp.status_code}, Size: {len(resp.text)} bytes")
    
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
    if not match:
        print("ERROR: No __NEXT_DATA__ found!")
        return
    
    data = json.loads(match.group(1))
    print(f"\n=== JSON Structure (top-level) ===")
    print(f"Keys: {list(data.keys())}")
    
    if 'props' in data:
        print(f"\n=== props ===")
        print_structure(data['props'], max_depth=3)
    
    # Find all strings containing "/article/"
    print(f"\n=== All strings containing '/article/' in __NEXT_DATA__ ===")
    urls = find_all_urls(data)
    for path, url in urls[:30]:
        print(f"  {path}: {url[:100]}")
    if len(urls) > 30:
        print(f"  ... ({len(urls) - 30} more)")
    print(f"Total: {len(urls)}")
    
    # Also check href regex fallback
    print(f"\n=== href regex fallback ===")
    hrefs = re.findall(r'href="(https://www\.scmp\.com/[^"\s]+article/\d+[^"\s]*)"', resp.text)
    print(f"Found {len(hrefs)} hrefs with /article/")
    for h in hrefs[:10]:
        print(f"  {h[:100]}")

if __name__ == "__main__":
    main()
