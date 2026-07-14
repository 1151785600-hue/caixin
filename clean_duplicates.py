"""Deduplicate articles in the repo.

Run inside GitHub Actions to avoid local git connectivity issues.

1. SCMP old-format files (scmp_XXXXX.html): delete if new-format (YYYYMMDD_scmp_XXXXX.html) exists
2. Caixin duplicate files (YYYYMMDD_HHMM_slug.html): keep only the latest per unique slug per date
"""
import os, re, glob, subprocess

def clean_scmp():
    """Remove old-format SCMP files that have a new-format counterpart."""
    scmp_dir = "articles/scmp"
    if not os.path.exists(scmp_dir):
        print("No scmp directory")
        return 0

    files = glob.glob(os.path.join(scmp_dir, "*.html"))
    old_files = [f for f in files if not os.path.basename(f)[0].isdigit()]
    new_files = [f for f in files if os.path.basename(f)[0].isdigit()]

    # Extract article IDs from new files
    new_ids = set()
    for f in new_files:
        m = re.search(r"scmp_(\d+)\.html$", os.path.basename(f))
        if m:
            new_ids.add(m.group(1))

    # Find old files whose ID exists in new files
    to_delete = []
    for f in old_files:
        m = re.search(r"scmp_(\d+)\.html$", os.path.basename(f))
        if m and m.group(1) in new_ids:
            to_delete.append(f)

    print(f"SCMP: {len(old_files)} old-format, {len(new_ids)} new-format IDs")
    print(f"SCMP: deleting {len(to_delete)} old duplicates")
    for f in to_delete:
        os.remove(f)
    return len(to_delete)


def clean_caixin():
    """Remove caixin duplicate files with HHMM time prefix."""
    caixin_dir = "articles"
    if not os.path.exists(caixin_dir):
        print("No articles directory")
        return 0

    # Only process files directly in articles/ (not in subdirectories)
    files = [f for f in glob.glob(os.path.join(caixin_dir, "*.html"))
             if os.path.isfile(f) and not f.startswith("_")]

    # Group by (date, slug) - slug is everything after date prefix
    groups = {}
    for f in files:
        fname = os.path.basename(f)
        # Pattern 1: YYYYMMDD_HHMM_slug.html (old format with time)
        # Pattern 2: YYYYMMDD_slug.html (new format without time)
        m = re.match(r"(\d{4}\d{2}\d{2})(?:_\d{4})?_(.+)\.html$", fname)
        if not m:
            # Try files without underscore after date
            m = re.match(r"(\d{4}\d{2}\d{2})(.+)\.html$", fname)
            if m:
                date, rest = m.group(1), m.group(2)
                # If rest starts with digits (time), strip them
                tm = re.match(r"(\d{4})_(.+)", rest)
                if tm:
                    date, rest = date, tm.group(2)
                groups.setdefault((date, rest), []).append(f)
            else:
                continue
        else:
            date, slug = m.group(1), m.group(2)
            groups.setdefault((date, slug), []).append(f)

    to_delete = []
    for (date, slug), group in groups.items():
        if len(group) > 1:
            # Sort by filename (latest time prefix wins - e.g. 2249 > 1612)
            group.sort(key=lambda x: os.path.basename(x), reverse=True)
            # Keep the first (latest), delete rest
            to_delete.extend(group[1:])

    print(f"Caixin: {len(files)} total, {len(groups)} unique articles")
    print(f"Caixin: deleting {len(to_delete)} duplicates")
    for f in to_delete:
        os.remove(f)
    return len(to_delete)


if __name__ == "__main__":
    d1 = clean_scmp()
    d2 = clean_caixin()

    # Git add and commit
    total = d1 + d2
    if total > 0:
        subprocess.run(["git", "add", "-A"], check=True)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if result.returncode != 0:
            subprocess.run(["git", "config", "user.name", "bot"], check=True)
            subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=True)
            subprocess.run([
                "git", "commit", "-m",
                f"chore: remove {total} duplicate article files (scmp:{d1} caixin:{d2})"
            ], check=True)
            subprocess.run(["git", "push"], check=True)
            print(f"Committed and pushed: {total} files removed")
        else:
            print("No changes to commit")
    else:
        print("No duplicates found")
