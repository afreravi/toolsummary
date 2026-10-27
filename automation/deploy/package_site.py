#!/usr/bin/env python3
"""Package the generated site as a deployable artifact.

The site is ~13 MB across ~1,000 files, which is too much churn to commit on
every refresh. Instead this writes a single archive that a human uploads to the
hosting panel by hand.

    python3 automation/deploy/package_site.py

Writes deploy/toolsummary-site.tar.gz and deploy/manifest.json, and prints what
the artifact contains. Exit code is 0 only when the site passed a basic sanity
check, so a broken build cannot be packaged by accident.
"""

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MVP = ROOT / "automation" / "mvp"
SITE = MVP / "site"
DEPLOY = ROOT / "deploy"
ARCHIVE = DEPLOY / "toolsummary-site.tar.gz"
MANIFEST = DEPLOY / "manifest.json"

# Files that must exist for the artifact to be worth uploading.
REQUIRED = ["index.html", "sitemap.xml", "llms.txt"]


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def check_site() -> list[str]:
    problems = []
    if not SITE.is_dir():
        return [f"site directory missing: {SITE}"]
    for name in REQUIRED:
        if not (SITE / name).is_file():
            problems.append(f"required file missing: {name}")

    index = SITE / "index.html"
    if index.is_file():
        html = index.read_text(encoding="utf-8", errors="replace")
        if "{{" in html:
            problems.append("index.html still contains a template placeholder")

    pages = list(SITE.rglob("index.html"))
    if len(pages) < 10:
        problems.append(f"only {len(pages)} pages rendered; expected hundreds")
    return problems


def data_generated_at() -> str | None:
    """Timestamp of the data the site was built from."""
    pricing = MVP / "data" / "pricing.json"
    if not pricing.is_file():
        return None
    try:
        return json.loads(pricing.read_text()).get("generated_at")
    except Exception:
        return None


def build() -> int:
    problems = check_site()
    if problems:
        print("refusing to package: site failed sanity checks", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    if DEPLOY.exists():
        shutil.rmtree(DEPLOY)
    DEPLOY.mkdir(parents=True)

    # Sorted names and a fixed mtime keep the archive byte-stable when the
    # underlying data has not changed, so an unchanged day produces an
    # identical artifact instead of a spurious diff.
    files = sorted(p for p in SITE.rglob("*") if p.is_file())
    with tarfile.open(ARCHIVE, "w:gz") as tar:
        for path in files:
            info = tar.gettarinfo(str(path), arcname=str(path.relative_to(SITE)))
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with open(path, "rb") as fh:
                tar.addfile(info, fh)

    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    model_dir = SITE / "model"
    compare_dir = SITE / "compare"
    model_pages = len(list(model_dir.rglob("index.html"))) if model_dir.is_dir() else 0
    compare_pages = len(list(compare_dir.rglob("index.html"))) if compare_dir.is_dir() else 0

    manifest = {
        "artifact": ARCHIVE.name,
        "sha256": digest,
        "bytes": ARCHIVE.stat().st_size,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_generated_at": data_generated_at(),
        "files": len(files),
        "model_pages": model_pages,
        "compare_pages": compare_pages,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"artifact   : {ARCHIVE.relative_to(ROOT)}")
    print(f"size       : {human(manifest['bytes'])}")
    print(f"files      : {manifest['files']}")
    print(f"model pages: {model_pages}")
    print(f"cmp pages  : {compare_pages}")
    print(f"sha256     : {digest[:16]}...")
    print(f"manifest   : {MANIFEST.relative_to(ROOT)}")
    print()
    print("Upload: extract into the web root on the host, replacing existing files.")
    print("Verify: check the sha256 above matches the archive you uploaded.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print-manifest", action="store_true",
                    help="print the manifest of the existing artifact and exit")
    a = ap.parse_args()

    if a.print_manifest:
        if not MANIFEST.is_file():
            print("no manifest yet; run package_site.py first", file=sys.stderr)
            return 1
        print(MANIFEST.read_text())
        return 0

    return build()


if __name__ == "__main__":
    raise SystemExit(main())
