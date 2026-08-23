#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 sliptonic <shopinthewoods@gmail.com>
"""Build the full site: the English site at build/site/ plus one site per language under
build/site/<lang>/ (the per-language-site pattern; languages exist for the wiki snapshot only,
so language playbooks read just the `wiki` branch).

    python3 tools/build_all.py [--base-url https://.../freecad-cam-docs] [--langs de,fr,pl]
"""
import argparse
import copy
import os
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_LANGS = ["de", "fr", "pl"]


def run(playbook_path, env_extra):
    env = dict(os.environ, **env_extra)
    r = subprocess.run(["npx", "antora", "--stacktrace", playbook_path], cwd=ROOT, env=env)
    if r.returncode != 0:
        sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="https://sliptonic.github.io/freecad-cam-docs")
    ap.add_argument("--langs", default=",".join(DEFAULT_LANGS))
    ap.add_argument("--playbook", default=os.path.join(ROOT, "antora-playbook.yml"))
    args = ap.parse_args()
    langs = [l for l in args.langs.split(",") if l]

    with open(args.playbook, encoding="utf-8") as fh:
        base = yaml.safe_load(fh)

    # English site
    en = copy.deepcopy(base)
    en["site"]["url"] = args.base_url
    with open(os.path.join(ROOT, "build-playbook-en.yml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump(en, fh, sort_keys=False)
    run("build-playbook-en.yml", {"SITE_LANGS": ",".join(langs)})

    for lang in langs:
        if not os.path.exists(os.path.join(ROOT, "l10n", lang, "antora.yml")):
            print(f"skip {lang}: no l10n/{lang}/antora.yml on this branch")
            continue
        pb = copy.deepcopy(base)
        pb["site"]["url"] = f"{args.base_url}/{lang}"
        pb["site"]["title"] = base["site"]["title"]
        for src in pb["content"]["sources"]:
            if src.get("url") == ".":
                src["branches"] = ["wiki"]
                src["start_path"] = f"l10n/{lang}"
                src.pop("edit_url", None)
        pb["output"]["dir"] = f"./build/site/{lang}"
        path = os.path.join(ROOT, f"build-playbook-{lang}.yml")
        with open(path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(pb, fh, sort_keys=False)
        run(f"build-playbook-{lang}.yml", {"SITE_LANG": lang, "SITE_LANGS": ",".join(langs)})
    print("built: en + " + ", ".join(langs))


if __name__ == "__main__":
    main()
