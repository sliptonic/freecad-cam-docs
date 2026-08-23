#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 sliptonic <shopinthewoods@gmail.com>
"""Import the FreeCAD wiki CAM pages (MediaWiki markup) into an Antora component.

Pipeline per page:
  1. strip translation plumbing (<translate>, <!--T:n-->, {{#translation:}}, <languages/>)
  2. convert wiki links and images to AsciiDoc macros (protected from pandoc by tokens)
  3. expand FreeCAD templates innermost-first (tools/templates.py), also protected by tokens
  4. pandoc -f mediawiki -t asciidoc
  5. restore tokens, add the page header (title, :page-origin:, :page-aliases:, GuiCommand
     attributes), normalize headings
  6. write modules/ROOT/pages/<path>.adoc

Also writes nav.adoc (from Template:CAM_Tools_navi), the page map (first run only), the image
download list, and build/migration-report.{json,html} plus pages/about/import-report.adoc.

Usage:
  python3 tools/import_wiki.py --source ~/FreeCAD-Documentation-Project/wiki --out modules/ROOT
  python3 tools/import_wiki.py ... --no-pandoc        # write pre-pass output for inspection
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import templates  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WIKI_BASE = "https://wiki.freecad.org/"

TOKEN_RE = re.compile(r"QQ(ADOC|TITLE)(\d{5})QQ")
TEMPLATE_RE = re.compile(r"\{\{(?!\{)((?:(?!\{\{)(?!\}\}).)*)\}\}", re.S)   # innermost {{…}}
LINK_RE = re.compile(r"\[\[([^\[\]]*?)\]\]")
EXT_LINK_RE = re.compile(r"\[(https?://[^\s\]]+)\s+([^\]]+)\]")
LANG_SUFFIX_RE = re.compile(r"/(?:[a-z]{2}(?:-[a-z]{2,4})?)$")
HEADING_RE = re.compile(r"^(={1,6})\s*(.*?)\s*=+\s*(?:<!--.*?-->)?\s*$", re.M)

NAV_GROUP_DIRS = {
    "Project Commands": "job",
    "Tool Commands": "inspect",
    "Basic Operations": "operations",
    "3D Operations": "operations",
    "CAM Dressup": "dressups",
    "Supplemental Commands": "operations",
    "CAM Modification": "modify",
    "Specialty Operations": "operations",
    "Miscellaneous": "misc",
    "ToolBit architecture": "tools",
    "Additional": "reference",
}
# Hand-tuned placements that the group rule gets wrong.
PATH_OVERRIDES = {
    "CAM_Workbench": "index.adoc",
    "CAM_ToolBitLibraryOpen": "tools/library-manager.adoc",
    "CAM_ToolBitDock": "tools/add-toolbit.adoc",
    "CAM_ToolBit_Library": "tools/toolbit-library.adoc",
    "CAM_ToolBit": "tools/toolbit.adoc",
    "CAM_ToolShape": "tools/tool-shape.adoc",
    "CAM_ToolController": "tools/tool-controller.adoc",
    "CAM_Tools": "tools/index.adoc",
    "CAM_Pocket_Shape": "operations/pocket.adoc",
    "CAM_Pocket3D": "operations/pocket-3d.adoc",
    "CAM_MillFace": "operations/mill-face.adoc",
    "CAM_Post": "output/post-process.adoc",
    "CAM_Postprocessor_Customization": "output/postprocessor-customization.adoc",
    "CAM_ExportTemplate": "job/export-template.adoc",
    "CAM_SetupSheet": "job/setup-sheet.adoc",
    "CAM_Fixture": "job/fixture.adoc",
    "CAM_Sanity": "job/sanity-check.adoc",
    "CAM_Job": "job/job.adoc",
    "CAM_Preferences": "reference/preferences.adoc",
    "CAM_scripting": "reference/scripting.adoc",
    "CAM_FAQ": "reference/faq.adoc",
    "CAM_experimental": "reference/experimental.adoc",
    "CAM_fourth_axis": "reference/fourth-axis.adoc",
    "CAM_Development_Roadmap": "contributing/development-roadmap.adoc",
    "CAM_Walkthrough_for_the_Impatient": "tutorials/walkthrough-for-the-impatient.adoc",
    "CAM_Shape": "operations/path-from-shape-tc.adoc",
    "CAM_Simulator": "inspect/simulator-legacy.adoc",
    "CAM_SimulatorGL": "inspect/simulator.adoc",
    "CAM_Copy": "modify/copy.adoc",
    "CAM_Array": "modify/array.adoc",
    "CAM_SimpleCopy": "modify/simple-copy.adoc",
    "CAM_Area": "misc/area.adoc",
    "CAM_Area_Workplane": "misc/area-workplane.adoc",
    "OpenCamLib": "reference/opencamlib.adoc",
    "Artwork_CAM": "reference/artwork.adoc",
}
EXTRA_PAGES = ["OpenCamLib", "Artwork_CAM"]
# Link targets that exist on the wiki only as redirects to CAM pages, or not at all but have an
# obvious current page. Resolved before the page map is consulted.
LINK_ALIASES = {
    "CAM_ToolLibraryEdit": "CAM_ToolBitLibraryOpen",
    "CAM_OperationCopy": "CAM_Copy",
    "CAM_Pocket_3D": "CAM_Pocket3D",
}


def load_path_redirects(src):
    """Path_* pages are all redirects to CAM_* pages; use them to resolve old links."""
    out = {}
    for f in os.listdir(src):
        if f.startswith("Path_") and f.endswith(".wikitext"):
            with open(os.path.join(src, f), encoding="utf-8") as fh:
                m = re.match(r"\s*#REDIRECT\s*\[\[([^\]|]+)", fh.read(300), re.I)
            if m:
                out[f[:-9]] = LANG_SUFFIX_RE.sub("", m.group(1).strip()).replace(" ", "_")
    return out


class PageCtx:
    def __init__(self, name, lang=None):
        self.name = name
        self.lang = lang
        self.properties = []
        self.version_tags = {}
        self.guicommand = {}
        self.tokens = {}
        self.ntok = 0
        self.unsupported = {}
        self.links = {"xref": 0, "wiki": 0, "unresolved": [], "external": 0, "anchor": 0}
        self.images = []
        self.warnings = []
        self.infobox_icon = None

    def protect(self, adoc, kind="ADOC"):
        self.ntok += 1
        tok = f"QQ{kind}{self.ntok:05d}QQ"
        self.tokens[tok] = adoc
        return tok

    def block_title(self, title):
        return self.protect(title, "TITLE")


# ---------------------------------------------------------------- selection & mapping

def default_path(name):
    slug = re.sub(r"^CAM_", "", name)
    slug = re.sub(r"^Dressup", "", slug) if name.startswith("CAM_Dressup") else slug
    slug = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", slug).replace("_", "-").lower()
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug + ".adoc"


def parse_navi(text):
    """Template:CAM_Tools_navi → ordered list of (group, [(page, label), …])."""
    groups = []
    for m in re.finditer(r"^\*\s*'''(.+?):'''\s*(.*)$", text, re.M):
        group, rest = m.group(1).strip(), m.group(2)
        items = []
        for lm in re.finditer(r"\[\[([^|\]]+?)(?:\{\{#translation:\}\})?\|([^\]]+)\]\]", rest):
            items.append((lm.group(1).strip().replace(" ", "_"), lm.group(2).strip()))
        groups.append((group, items))
    return groups


def build_page_map(pages, navi_groups, existing):
    pmap = dict(existing or {})
    group_of = {}
    for g, items in navi_groups:
        for page, _ in items:
            group_of.setdefault(page, g)
    for name in pages:
        if name in pmap:
            continue
        if name in PATH_OVERRIDES:
            pmap[name] = PATH_OVERRIDES[name]
            continue
        d = NAV_GROUP_DIRS.get(group_of.get(name, ""), "")
        pmap[name] = (d + "/" if d else "") + default_path(name)
    return pmap


# ---------------------------------------------------------------- wikitext pre-pass

def strip_plumbing(text):
    text = re.sub(r"<languages\s*/>", "", text)
    text = re.sub(r"</?translate>", "", text)
    text = re.sub(r"<!--\s*T:\d+\s*-->", "", text)
    text = text.replace("{{#translation:}}", "")
    text = re.sub(r"\{\{#translation:\}\}", "", text)
    # Translated pages carry '<span id="English"></span>' shims above headings to keep the
    # English anchors valid; the importer's anchors come from the visible headings instead.
    text = re.sub(r"<span id=\"[^\"]*\"></span>\s*", "", text)
    return text


def anchor_id(s):
    s = html.unescape(s).strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-")


def convert_link(target, label, ctx, page_map, images):
    target = target.strip()
    if not target:
        return label or ""
    low = target.lower()
    if low.startswith(("image:", "file:")):
        return convert_image(target, label, ctx, images)
    if low.startswith((":category:", "category:")):
        return ""
    if target.startswith("#"):
        ctx.links["anchor"] += 1
        return f"<<{anchor_id(target[1:])},{label or target[1:]}>>"
    page, _, frag = target.partition("#")
    page = LANG_SUFFIX_RE.sub("", page.strip()).replace(" ", "_")
    text = label if label is not None else page.replace("_", " ")
    page = LINK_ALIASES.get(page, page)
    if page in page_map:
        ctx.links["xref"] += 1
        anchor = f"#{anchor_id(frag)}" if frag else ""
        return f"xref:{page_map[page]}{anchor}[{text}]"
    ctx.links["wiki"] += 1
    if page.startswith(("CAM_", "Path_")):
        ctx.links["unresolved"].append(page)
    url = WIKI_BASE + page + (f"#{frag.replace(' ', '_')}" if frag else "")
    return f"{url}[{text}]"


def convert_image(target, label, ctx, images):
    name = target.split(":", 1)[1].strip()
    name = name.replace(" ", "_")
    name = name[:1].upper() + name[1:]        # MediaWiki file titles are first-letter capitalized
    parts = [p.strip() for p in (label or "").split("|")] if label else []
    # In wikitext the label we receive is everything after the first '|', re-split here.
    width = None
    caption = ""
    block = False
    for p in parts:
        if re.fullmatch(r"\d+px", p):
            width = p[:-2]
        elif p in ("thumb", "frame", "framed", "center", "left", "right", "none"):
            block = True
        elif p.startswith("link="):
            pass
        elif p:
            caption = p
    images.add(name)
    ctx.images.append(name)
    attrs = []
    if caption:
        attrs.append(caption.replace("]", "\\]"))
    if width:
        attrs.append(f"{width}" if caption else f"width={width}")
    if block or (width and int(width) >= 300):
        return f"\n\nimage::{name}[{','.join(attrs)}]\n\n"
    return f"image:{name}[{','.join(attrs)}]"


def convert_links(text, ctx, page_map, images):
    def repl(m):
        inner = m.group(1)
        target, sep, label = inner.partition("|")
        if sep and "{{" in label:
            label = expand_templates(label, ctx)     # e.g. [[CAM_experimental|{{Emphasis|Experimental}}]]
        if target.strip().lower().startswith(("image:", "file:")):
            return ctx.protect(convert_image(target, label if sep else None, ctx, images))
        return ctx.protect(convert_link(target, label if sep else None, ctx, page_map, images))
    # Links whose label holds a template contain '{{…|…}}' with a pipe, which the simple
    # partition above handles because the first pipe separates target from label.
    return LINK_RE.sub(repl, text)


def split_args(argstr):
    pos, named = [], {}
    for raw in argstr.split("|"):
        if "=" in raw and not raw.lstrip().startswith("http"):
            k, _, v = raw.partition("=")
            if re.fullmatch(r"\s*[A-Za-z][A-Za-z0-9 _/-]*\s*", k):
                named[k.strip()] = v
                continue
        pos.append(raw)
    return pos, named


def expand_templates(text, ctx):
    for _ in range(50):
        changed = False

        def repl(m):
            nonlocal changed
            body = m.group(1)
            name, _, argstr = body.partition("|")
            pos, named = split_args(argstr) if argstr else ([], {})
            out = templates.handle(name, pos, named, ctx)
            if out is None:
                key = templates.normalize_name(name)
                ctx.unsupported[key] = ctx.unsupported.get(key, 0) + 1
                return "QQKEEP" + m.group(0)[2:-2].replace("|", "QQPIPE") + "QQEND"
            changed = True
            if not out:
                return ""
            if TOKEN_RE.fullmatch(out.strip()):
                return out.strip()          # already protected (e.g. a block title)
            return ctx.protect(out)

        text = TEMPLATE_RE.sub(repl, text)
        if not changed:
            break
    text = re.sub(r"QQKEEP(.*?)QQEND", lambda m: "{{" + m.group(1).replace("QQPIPE", "|") + "}}", text, flags=re.S)
    return text


def pre_pass(text, ctx, page_map, images):
    text = strip_plumbing(text)
    text = convert_links(text, ctx, page_map, images)
    text = expand_templates(text, ctx)
    return text


# ---------------------------------------------------------------- pandoc & post-pass

def run_pandoc(text):
    r = subprocess.run(
        ["pandoc", "-f", "mediawiki", "-t", "asciidoc", "--wrap=none"],
        input=text, capture_output=True, text=True, check=False,
    )
    return r.stdout, r.stderr.strip()


def restore_tokens(text, ctx):
    def repl(m):
        tok = m.group(0)
        val = ctx.tokens.get(tok, tok)
        if m.group(1) == "TITLE":
            return f"\n.{val}\nQQNOBLANK"
        return val
    # Token values may themselves contain tokens (a button holding an icon and a link); repeat
    # until none remain.
    for _ in range(6):
        new = TOKEN_RE.sub(repl, text)
        if new == text:
            break
        text = new
    text = re.sub(r"QQNOBLANK\n+", "", text)
    # pandoc may wrap tokens in escapes or emphasis; clean the common residue
    text = text.replace("\\{", "{").replace("\\}", "}")
    return text


def normalize_headings(adoc):
    """Promote headings one level and drop pandoc's explicit anchors.

    The wiki's top-level sections are '== X ==' (MediaWiki level 2); pandoc writes them as
    '=== X', one level below where they belong under the '= Title' line. Pandoc also precedes
    each heading with an explicit '[[x_y]]' anchor using underscores; we remove it so
    Asciidoctor generates ids with the site's idseparator ('-'), which is what the xref
    anchors produced by convert_link() use.
    """
    lines = []
    prev_level = 1          # the document title
    in_block = False        # skip fenced blocks (----, ....) where '=' lines are content
    for line in adoc.split("\n"):
        if re.fullmatch(r"(----|\.\.\.\.|====|\+\+\+\+)", line.strip()):
            in_block = not in_block
            lines.append(line)
            continue
        if in_block:
            lines.append(line)
            continue
        if re.fullmatch(r"\[\[[^\]]+\]\]", line.strip()):
            continue
        m = re.match(r"^(={1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            if level == 1:
                level = 2                     # a stray '= X' in the body
            else:
                level = max(2, level - 1)     # promote: wiki '==' is the first body level
            if level > prev_level + 1:        # no skipped levels (Asciidoctor warns)
                level = prev_level + 1
            prev_level = level
            line = "=" * level + " " + m.group(2)
        lines.append(line)
    return "\n".join(lines)


def page_title(name, ctx):
    g = ctx.guicommand or {}
    t = None
    if ctx.lang:
        t = g.get(f"name/{ctx.lang}")
    t = t or g.get("name")
    if t:
        return plain(t, ctx)
    return name.replace("_", " ")


def plain(text, ctx):
    """Restore tokens and reduce AsciiDoc macros to plain text for use in page attributes."""
    text = restore_tokens(text, ctx)
    text = re.sub(r"image:[^\[]+\[[^\]]*\]\s*", "", text)
    text = re.sub(r"xref:[^\[]+\[([^\]]*)\]", r"\1", text)
    text = re.sub(r"https?://\S+\[([^\]]*)\]", r"\1", text)
    text = re.sub(r"kbd:\[([^\]]*)\]", r"\1", text)
    text = re.sub(r"btn:\[([^\]]*)\]", r"\1", text)
    text = re.sub(r"menu:([^\[]+)\[([^\]]*)\]", lambda m: m.group(1) + (" → " + m.group(2) if m.group(2) else ""), text)
    return re.sub(r"\s+", " ", text).strip()


def header(name, path, ctx, aliases, revision):
    lines = [f"= {page_title(name, ctx)}"]
    suffix = f"/{ctx.lang}" if ctx.lang else ""
    lines.append(f":page-origin: {WIKI_BASE}{name}{suffix}")
    if revision:
        lines.append(f":page-origin-revision: {revision}")
    if aliases:
        lines.append(":page-aliases: " + ", ".join(aliases))
    g = ctx.guicommand or {}
    if g:
        lines.append(f":page-command: {name}")
    if ctx.infobox_icon:
        lines.append(f":page-icon: {ctx.infobox_icon}")
    if g.get("menulocation"):
        lines.append(f":page-menu: {plain(g['menulocation'], ctx)}")
    if g.get("workbenches"):
        lines.append(f":page-workbench: {plain(g['workbenches'], ctx)}")
    if g.get("shortcut"):
        lines.append(f":page-shortcut: {plain(g['shortcut'], ctx)}")
    if g.get("version"):
        lines.append(f":page-since: {plain(g['version'], ctx)}")
    if g.get("seealso"):
        lines.append(f":page-see-also: {plain(g['seealso'], ctx)}")
    lines.append(":page-imported: true")
    lines.append("")
    return "\n".join(lines)


def fix_lists(adoc):
    """Repair two pandoc list outputs Asciidoctor rejects.

    - A wiki list item that follows a blank line loses its list context and pandoc emits the
      raw marker as '++#*++ text'; turn the marker back into AsciiDoc list syntax.
    - Pandoc writes alphabetic lists with literal 'A.', 'B.' markers; Asciidoctor wants the
      same marker on every item, so use the generic '.' and a style attribute.
    """
    out = []
    for line in adoc.split("\n"):
        m = re.match(r"^\+\+([#*:;]+)\+\+\s*(.*)$", line)
        if m:
            marker = "".join("." if c == "#" else "*" for c in m.group(1))
            line = f"{marker} {m.group(2)}"
        m = re.match(r"^([A-Z])\.\s+(.*)$", line)
        if m:
            if m.group(1) == "A":
                out.append("[upperalpha]")
            line = f". {m.group(2)}"
        out.append(line)
    return "\n".join(out)


def post_pass(adoc, name, path, ctx, aliases, revision):
    adoc = restore_tokens(adoc, ctx)
    adoc = fix_lists(adoc)
    adoc = normalize_headings(adoc)
    adoc = re.sub(r"\n{3,}", "\n\n", adoc).strip() + "\n"
    return header(name, path, ctx, aliases, revision) + "\n" + adoc


# ---------------------------------------------------------------- nav

def write_nav(out_dir, navi_groups, page_map, pages, redirects, titles=None, lang=None):
    titles = titles or {}

    def label_for(page, default):
        t = titles.get(page)
        if t and lang:
            return t
        return default

    lines = [f"* xref:index.adoc[{label_for('CAM_Workbench', 'CAM Workbench')}]"]
    placed = {"CAM_Workbench"}
    for group, items in navi_groups:
        entries = [(p, l) for p, l in items if p in page_map and p in pages and p not in placed]
        if not entries:
            continue
        lines.append(f"* {group}")
        for p, label in entries:
            lines.append(f"** xref:{page_map[p]}[{label_for(p, label)}]")
            placed.add(p)
    rest = [p for p in pages if p not in placed and p not in redirects]
    if rest:
        lines.append("* Other pages")
        for p in sorted(rest):
            lines.append(f"** xref:{page_map[p]}[{label_for(p, p.replace('_', ' '))}]")
    if not lang:
        lines.append("* About")
        lines.append("** xref:about/import-report.adoc[Import report]")
    with open(os.path.join(out_dir, "nav.adoc"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------- report

def write_report(report, out_dir, build_dir):
    os.makedirs(build_dir, exist_ok=True)
    with open(os.path.join(build_dir, "migration-report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    s = report["summary"]
    rows = []
    for name, p in sorted(report["pages"].items()):
        issues = []
        if p["unsupported"]:
            issues.append("templates: " + ", ".join(f"{k}×{v}" for k, v in p["unsupported"].items()))
        if p["links"]["unresolved"]:
            issues.append("unresolved: " + ", ".join(sorted(set(p["links"]["unresolved"]))))
        if p["pandoc_stderr"]:
            issues.append("pandoc: " + p["pandoc_stderr"][:120])
        rows.append((name, p["path"], p["links"]["xref"], p["links"]["wiki"], len(p["images"]),
                     ", ".join(f"{k}×{v}" for k, v in sorted(p["version_tags"].items())), "; ".join(issues)))
    adoc = [
        "= Import report",
        ":page-status: generated",
        "",
        f"Generated {report['generated']} from the wiki bridge repository (sync {report['source_sync']}).",
        "",
        "[cols=\"1,1\"]",
        "|===",
        f"| Pages selected | {s['pages_selected']}",
        f"| Pages written | {s['pages_written']}",
        f"| Redirects turned into aliases | {s['aliases']}",
        f"| Internal links resolved to xref | {s['links_xref']}",
        f"| Links left pointing at the wiki | {s['links_wiki']}",
        f"| Links to missing CAM pages | {s['links_unresolved']}",
        f"| Images referenced | {s['images_referenced']}",
        f"| Templates expanded | {s['templates_expanded']}",
        f"| Templates unsupported | {s['templates_unsupported']}",
        f"| Pages needing manual review | {s['manual_review']}",
        "|===",
        "",
        "== Templates",
        "",
        "[cols=\"2,1\"]",
        "|===",
        "| Template | Uses",
    ] + [f"| `{k}` | {v}" for k, v in sorted(report["templates"].items(), key=lambda kv: -kv[1])] + [
        "|===",
        "",
        "== Pages",
        "",
        "[cols=\"2,2,1,1,1,1,3\",options=\"header\"]",
        "|===",
        "| Wiki page | Path | xref | wiki links | images | version markers | Issues",
    ] + [f"| {a} | `{b}` | {c} | {d} | {e} | {f} | {g}" for a, b, c, d, e, f, g in rows] + ["|==="]
    about = os.path.join(out_dir, "pages", "about")
    os.makedirs(about, exist_ok=True)
    with open(os.path.join(about, "import-report.adoc"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(adoc) + "\n")
    with open(os.path.join(build_dir, "migration-report.html"), "w", encoding="utf-8") as fh:
        fh.write("<meta charset=utf-8><title>Migration report</title><pre>" + html.escape(json.dumps(s, indent=2)) + "</pre>")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="wiki directory of the bridge repo")
    ap.add_argument("--out", default=os.path.join(ROOT, "modules", "ROOT"))
    ap.add_argument("--page-map", default=os.path.join(HERE, "page_map.yml"))
    ap.add_argument("--build-dir", default=os.path.join(ROOT, "build"))
    ap.add_argument("--no-pandoc", action="store_true", help="write pre-pass text instead of AsciiDoc")
    ap.add_argument("--only", help="comma-separated page names to process")
    ap.add_argument("--lang", help="import a translation: read <source>/<lang>, write l10n/<lang>/modules/ROOT")
    args = ap.parse_args()

    root_src = args.source
    src = os.path.join(root_src, args.lang) if args.lang else root_src
    en_names = sorted(f[:-9] for f in os.listdir(root_src) if f.startswith("CAM_") and f.endswith(".wikitext"))
    names = sorted(f[:-9] for f in os.listdir(src) if f.startswith("CAM_") and f.endswith(".wikitext"))
    names += [n for n in EXTRA_PAGES if os.path.exists(os.path.join(src, n + ".wikitext"))]

    # redirects → aliases
    redirects = {}
    for n in list(names):
        with open(os.path.join(src, n + ".wikitext"), encoding="utf-8") as fh:
            head = fh.read(200)
        m = re.match(r"\s*#REDIRECT\s*\[\[([^\]|]+)", head, re.I)
        if m:
            redirects[n] = LANG_SUFFIX_RE.sub("", m.group(1).strip()).replace(" ", "_")
    pages = [n for n in names if n not in redirects]

    navi_path = os.path.join(root_src, "Template;CAM_Tools_navi.wikitext")
    navi_groups = parse_navi(open(navi_path, encoding="utf-8").read()) if os.path.exists(navi_path) else []

    existing = {}
    if os.path.exists(args.page_map):
        with open(args.page_map, encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}
    en_redirects = {}
    for n in en_names:
        with open(os.path.join(root_src, n + ".wikitext"), encoding="utf-8") as fh:
            m = re.match(r"\s*#REDIRECT\s*\[\[([^\]|]+)", fh.read(200), re.I)
        if m:
            en_redirects[n] = LANG_SUFFIX_RE.sub("", m.group(1).strip()).replace(" ", "_")
    en_pages = [n for n in en_names if n not in en_redirects] + EXTRA_PAGES
    page_map = build_page_map(en_pages, navi_groups, existing.get("pages"))
    for r, target in redirects.items():
        if target in page_map:
            page_map[r] = page_map[target]
    for r, target in en_redirects.items():
        if target in page_map:
            page_map.setdefault(r, page_map[target])
    for r, target in load_path_redirects(root_src).items():
        target = LINK_ALIASES.get(target, target)
        if target in page_map and r not in page_map:
            page_map[r] = page_map[target]
    if not existing:
        with open(args.page_map, "w", encoding="utf-8") as fh:
            yaml.safe_dump({"pages": {k: v for k, v in page_map.items() if k not in redirects},
                            "redirects": redirects, "extra_pages": EXTRA_PAGES}, fh, sort_keys=True, allow_unicode=True)

    aliases = {}
    for r, target in redirects.items():
        aliases.setdefault(target, []).append(r + ".adoc")
    for n in names:
        aliases.setdefault(n, [])

    try:
        toplevel = subprocess.run(["git", "-C", src, "rev-parse", "--show-toplevel"],
                                  capture_output=True, text=True).stdout.strip()
        sync = subprocess.run(["git", "-C", toplevel, "log", "-1", "--format=%ad", "--date=short"],
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        toplevel, sync = "", "unknown"

    if args.lang:
        args.out = os.path.join(ROOT, "l10n", args.lang, "modules", "ROOT")
    only = set(args.only.split(",")) if args.only else None
    images = set()
    report = {"generated": dt.date.today().isoformat(), "source_sync": sync, "pages": {}, "templates": {}}
    titles = {}
    pages_dir = os.path.join(args.out, "pages")
    written = 0
    for name in pages:
        if only and name not in only:
            continue
        with open(os.path.join(src, name + ".wikitext"), encoding="utf-8") as fh:
            wikitext = fh.read()
        rev = ""
        if toplevel:
            try:
                relpath = os.path.relpath(os.path.join(src, name + ".wikitext"), toplevel)
                rev = subprocess.run(["git", "-C", toplevel, "log", "-1", "--format=%h %ad", "--date=short",
                                      "--", relpath], capture_output=True, text=True, timeout=30).stdout.strip()
            except Exception:
                rev = ""
        ctx = PageCtx(name, lang=args.lang)
        pre = pre_pass(wikitext, ctx, page_map, images)
        if ctx.infobox_icon:
            images.add(ctx.infobox_icon)
            ctx.images.append(ctx.infobox_icon)
        path = page_map[name]
        dest = os.path.join(pages_dir, path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        stderr = ""
        if args.no_pandoc:
            out = pre
            dest = dest[:-5] + ".pre.txt"
        else:
            adoc, stderr = run_pandoc(pre)
            out = post_pass(adoc, name, path, ctx, aliases.get(name), rev)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(out)
        written += 1
        for k, v in ctx.unsupported.items():
            report["templates"][k] = report["templates"].get(k, 0) + v
        report["pages"][name] = {
            "path": path, "links": ctx.links, "images": ctx.images, "version_tags": ctx.version_tags,
            "unsupported": ctx.unsupported, "properties": ctx.properties, "pandoc_stderr": stderr,
            "guicommand": ctx.guicommand, "tokens": ctx.ntok,
        }
        titles[name] = page_title(name, ctx)

    # template usage counts for the report (expanded ones)
    tcount = {}
    for name in pages:
        with open(os.path.join(src, name + ".wikitext"), encoding="utf-8") as fh:
            for m in re.finditer(r"\{\{\s*([A-Za-z_#: -]+?)\s*(?:\||\}\})", fh.read()):
                k = templates.normalize_name(m.group(1))
                tcount[k] = tcount.get(k, 0) + 1
    report["templates"] = {**tcount, **{f"UNSUPPORTED {k}": v for k, v in report["templates"].items()}}

    P = report["pages"]
    manual = [n for n, p in P.items() if p["unsupported"] or p["links"]["unresolved"] or p["pandoc_stderr"]]
    report["summary"] = {
        "pages_selected": len(names), "pages_written": written, "aliases": len(redirects),
        "links_xref": sum(p["links"]["xref"] for p in P.values()),
        "links_wiki": sum(p["links"]["wiki"] for p in P.values()),
        "links_unresolved": sum(len(p["links"]["unresolved"]) for p in P.values()),
        "images_referenced": len(images),
        "templates_expanded": sum(v for k, v in tcount.items()),
        "templates_unsupported": sum(v for k, v in report["templates"].items() if k.startswith("UNSUPPORTED")),
        "manual_review": len(manual),
    }
    report["manual_review"] = sorted(manual)
    report["images"] = sorted(images)

    if args.lang and not args.no_pandoc and not only:
        # Stub the English pages this language does not translate, so every nav entry exists.
        missing = [n for n in en_pages if n not in set(pages)]
        for n in missing:
            dest = os.path.join(pages_dir, page_map[n])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            html_path = page_map[n][:-5] + ".html"
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(f"""= {n.replace('_', ' ')}
:page-status: untranslated

This page has not been translated. The English page is at
link:{{site-en-url}}/cam/{{page-component-version}}/{html_path}[{n.replace('_', ' ')}].
""")
        write_nav(args.out, navi_groups, page_map, en_pages, redirects, titles=titles, lang=args.lang)
        with open(os.path.join(ROOT, "l10n", args.lang, "antora.yml"), "w", encoding="utf-8") as fh:
            fh.write(f"""name: cam
title: FreeCAD CAM
version: wiki-2026-08
display_version: Wiki (Aug 2026)
start_page: index.adoc
nav:
  - modules/ROOT/nav.adoc
asciidoc:
  attributes:
    site-en-url: https://sliptonic.github.io/freecad-cam-docs
    page-component-version: wiki-2026-08
""")
        print(f"stubbed {len(missing)} untranslated pages")
    elif not args.no_pandoc and not only:
        write_nav(args.out, navi_groups, page_map, pages, redirects)
        write_report(report, args.out, args.build_dir)
    imgname = f"images-{args.lang}.txt" if args.lang else "images.txt"
    with open(os.path.join(args.build_dir if os.path.isdir(args.build_dir) else HERE, imgname), "w") as fh:
        fh.write("\n".join(sorted(images)) + "\n")
    print(json.dumps(report["summary"], indent=2))
    if manual:
        print("manual review:", ", ".join(manual))


if __name__ == "__main__":
    main()
