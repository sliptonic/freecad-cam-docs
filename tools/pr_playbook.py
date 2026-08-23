#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 sliptonic <shopinthewoods@gmail.com>
"""Emit a playbook for pull-request builds.

The PR's checked-out content (Antora ref ``HEAD``) replaces the branch the PR targets, so the
preview shows the proposed change next to the other documentation version(s).

    python3 tools/pr_playbook.py --base DEV --url https://.../pr-42 > antora-playbook-pr.yml
"""
import argparse
import sys

import yaml

CONTENT_BRANCHES = ["wiki", "audit", "DEV"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="branch the pull request targets")
    ap.add_argument("--url", required=True, help="site URL of the preview deployment")
    ap.add_argument("--playbook", default="antora-playbook.yml")
    args = ap.parse_args()

    with open(args.playbook, encoding="utf-8") as fh:
        pb = yaml.safe_load(fh)

    refs = [b for b in CONTENT_BRANCHES if b != args.base] + ["HEAD"]
    for src in pb["content"]["sources"]:
        if src.get("url") == ".":
            src["branches"] = refs
    pb["site"]["url"] = args.url
    pb["site"]["title"] = pb["site"]["title"] + " — pull request preview"
    yaml.safe_dump(pb, sys.stdout, sort_keys=False)


if __name__ == "__main__":
    main()
