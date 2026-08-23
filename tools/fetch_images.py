#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 sliptonic <shopinthewoods@gmail.com>
"""Download the images referenced by imported pages from the FreeCAD wiki.

    python3 tools/fetch_images.py --list build/images.txt --out modules/ROOT/images

Uses the MediaWiki API (action=query&prop=imageinfo) to resolve each File: name to its URL.
Existing files are not re-downloaded. Missing files are listed in build/images-missing.txt.
"""
import argparse
import os
import sys
import time

import requests

API = "https://wiki.freecad.org/api.php"
UA = "freecad-cam-docs importer (https://github.com/sliptonic/freecad-cam-docs)"


def resolve(session, names):
    urls = {}
    for i in range(0, len(names), 50):
        batch = names[i:i + 50]
        r = session.get(API, params={
            "action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url",
            "titles": "|".join("File:" + n for n in batch),
        }, timeout=60)
        r.raise_for_status()
        for page in r.json().get("query", {}).get("pages", {}).values():
            title = page.get("title", "")[5:].replace(" ", "_")
            info = page.get("imageinfo")
            if info:
                urls[title] = info[0]["url"]
        time.sleep(0.5)
    return urls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    names = [l.strip() for l in open(args.list, encoding="utf-8") if l.strip()]
    os.makedirs(args.out, exist_ok=True)
    todo = [n for n in names if not os.path.exists(os.path.join(args.out, n))]
    s = requests.Session()
    s.headers["User-Agent"] = UA
    urls = resolve(s, todo)
    missing = []
    for n in todo:
        url = urls.get(n)
        if not url:
            missing.append(n)
            continue
        r = s.get(url, timeout=120)
        if r.status_code != 200:
            missing.append(n)
            continue
        with open(os.path.join(args.out, n), "wb") as fh:
            fh.write(r.content)
        time.sleep(0.2)
    with open(os.path.join(os.path.dirname(args.list), "images-missing.txt"), "w") as fh:
        fh.write("\n".join(missing) + ("\n" if missing else ""))
    print(f"requested {len(names)}, already present {len(names) - len(todo)}, fetched {len(todo) - len(missing)}, missing {len(missing)}")
    if missing:
        print("missing:", ", ".join(missing), file=sys.stderr)


if __name__ == "__main__":
    main()
