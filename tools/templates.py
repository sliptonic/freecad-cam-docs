# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 sliptonic <shopinthewoods@gmail.com>
"""FreeCAD wiki template handlers for the wikitext → AsciiDoc importer.

Each handler receives the template's positional and named arguments and returns AsciiDoc text.
Handlers never see nested templates: the caller expands innermost templates first. Wiki links
inside arguments arrive already converted to AsciiDoc (xref:/link: macros) by the caller.

Returned text is protected from pandoc by the caller (it is stored and replaced by a token), so
handlers may return any AsciiDoc, including block-level constructs. A handler that returns
``None`` declares the template unsupported; the caller leaves it in place and reports it.
"""
import re

ARROW_RE = re.compile(r"\s*(?:→|->|→|»|>)\s*")
TOKEN_RE = re.compile(r"QQ(?:ADOC|TITLE)\d{5}QQ")


def _strip_tokens(s):
    """Remove protected inline content (icons, links) that cannot nest inside a UI macro."""
    return re.sub(r"\s*QQ(?:ADOC|TITLE)\d{5}QQ\s*", " ", s).strip()

# Templates that carry navigation or translation plumbing and have no AsciiDoc equivalent.
DROP = {
    "docnav", "userdocnavi", "powerdocnavi", "cam_tools_navi", "cam tools navi", "top",
    "tocright", "tocleft", "clear", "#translation:", "translation", "languages",
    "unfinisheddocu_navi", "tutorials navi", "tutorials_navi",
}


def _text(s):
    return (s or "").strip()


def menu_command(pos, named, ctx):
    path = _strip_tokens(_text(pos[0])) if pos else ""
    parts = [p.strip() for p in ARROW_RE.split(path) if p.strip()]
    if not parts:
        return ""
    if len(parts) == 1:
        return f"menu:{parts[0]}[]"
    return f"menu:{parts[0]}[{' > '.join(parts[1:])}]"


def key(pos, named, ctx):
    if not pos:
        return ""
    txt = _text(pos[0])
    if TOKEN_RE.search(txt):
        return txt          # {{KEY|[[Image:…]] [[Page|label]]}} — an icon-plus-link, not a key
    return f"kbd:[{txt}]"


def button(pos, named, ctx):
    if not pos:
        return ""
    txt = _text(pos[0])
    if TOKEN_RE.search(txt):
        # The button label is an icon plus a link (toolbar buttons on the wiki): keep both,
        # drop the macro, which cannot contain nested brackets.
        return txt
    return f"btn:[{txt}]"


def property_data(pos, named, ctx):
    name = _text(pos[0]) if pos else ""
    ptype = _text(pos[1]) if len(pos) > 1 else ""
    ctx.properties.append({"name": name, "type": ptype, "view": False})
    return f"*{name}*" + (f" (`{ptype}`)" if ptype else "")


def property_view(pos, named, ctx):
    name = _text(pos[0]) if pos else ""
    ptype = _text(pos[1]) if len(pos) > 1 else ""
    ctx.properties.append({"name": name, "type": ptype, "view": True})
    return f"*{name}*" + (f" (`{ptype}`)" if ptype else "")


def title_property(pos, named, ctx):
    # A group heading inside a property list: becomes a block title for the list that follows.
    return ctx.block_title(_text(pos[0]) if pos else "")


def code(pos, named, ctx):
    src = named.get("code")
    if src is None:
        src = pos[0] if pos else ""
    lang = _text(named.get("lang", "python")) or "python"
    src = src.strip("\n")
    return f"\n[source,{lang}]\n----\n{src}\n----\n"


def incode(pos, named, ctx):
    return f"`{_text(pos[0])}`" if pos else ""


def filename(pos, named, ctx):
    return f"`{_text(pos[0])}`" if pos else ""


def value(pos, named, ctx):
    return f"`{_text(pos[0])}`" if pos else ""


def emphasis(pos, named, ctx):
    return f"_{_text(pos[0])}_" if pos else ""


def version(pos, named, ctx):
    v = _text(pos[0]) if pos else ""
    ctx.version_tags[v] = ctx.version_tags.get(v, 0) + 1
    return f"[.since]#introduced in {v}#" if v else ""


def version_plus(pos, named, ctx):
    v = _text(pos[0]) if pos else ""
    ctx.version_tags[v] = ctx.version_tags.get(v, 0) + 1
    return f"[.since]#{v} and later#" if v else ""


def version_minus(pos, named, ctx):
    v = _text(pos[0]) if pos else ""
    ctx.version_tags[v] = ctx.version_tags.get(v, 0) + 1
    return f"[.until]#{v} and earlier#" if v else ""


def obsolete(pos, named, ctx):
    v = _text(pos[0]) if pos else ""
    ctx.version_tags[v] = ctx.version_tags.get(v, 0) + 1
    return f"[.obsolete]#obsolete since {v}#" if v else "[.obsolete]#obsolete#"


def caption(pos, named, ctx):
    txt = _text(pos[0]) if pos else ""
    return f"\n[.caption]\n{txt}\n" if txt else ""


def unfinished(pos, named, ctx):
    return "\nNOTE: This page is incomplete; it was marked as unfinished on the wiki.\n"


def very_important(pos, named, ctx):
    txt = _text(pos[0]) if pos else ""
    return f"\nWARNING: {txt}\n" if txt else ""


def true_false(pos, named, ctx, word):
    return f"`{word}`"


def gui_command(pos, named, ctx):
    """{{GuiCommand|Name=…|MenuLocation=…|Workbenches=…|Shortcut=…|Version=…|SeeAlso=…}}"""
    g = {k.strip().lower(): _text(v) for k, v in named.items()}
    ctx.guicommand = g
    rows = []
    if g.get("menulocation"):
        rows.append(("Menu location", menu_command([g["menulocation"]], {}, ctx)))
    if g.get("workbenches"):
        rows.append(("Workbenches", g["workbenches"]))
    if g.get("shortcut"):
        keys = " ".join(f"kbd:[{k.strip()}]" for k in re.split(r"\s*(?:\+|then|,)\s*", g["shortcut"]) if k.strip())
        rows.append(("Default shortcut", keys or g["shortcut"]))
    if g.get("version"):
        rows.append(("Introduced in version", g["version"]))
    if g.get("seealso"):
        rows.append(("See also", g["seealso"]))
    if not rows:
        return ""
    body = "\n".join(f"{k}:: {v}" for k, v in rows)
    return f"\n[.guicommand]\n{body}\n"


def colored_text(pos, named, ctx):
    # {{ColoredText|color|text}} or {{ColoredText|text}}: keep the text, drop the color.
    txt = _text(pos[-1]) if pos else ""
    return txt


def tutorial_info(pos, named, ctx):
    g = {k.strip().lower(): _text(v) for k, v in named.items()}
    rows = [(k.title(), v) for k, v in g.items() if v]
    if not rows:
        return ""
    body = "\n".join(f"{k}:: {v}" for k, v in rows)
    return f"\n[.tutorialinfo]\n{body}\n"


HANDLERS = {
    "menucommand": menu_command,
    "key": key,
    "button": button,
    "propertydata": property_data,
    "propertyview": property_view,
    "titleproperty": title_property,
    "code": code,
    "incode": incode,
    "filename": filename,
    "value": value,
    "emphasis": emphasis,
    "version": version,
    "versionplus": version_plus,
    "versionminus": version_minus,
    "obsolete": obsolete,
    "caption": caption,
    "unfinisheddocu": unfinished,
    "veryimportantmessage": very_important,
    "guicommand": gui_command,
    "tutorialinfo": tutorial_info,
    "coloredtext": colored_text,
    "true": lambda p, n, c: true_false(p, n, c, "true"),
    "false": lambda p, n, c: true_false(p, n, c, "false"),
}


def normalize_name(name):
    return name.strip().lower().replace(" ", "_")


def handle(name, pos, named, ctx):
    """Return AsciiDoc for a template, '' to drop it, or None if unsupported."""
    key_ = normalize_name(name)
    if key_ in DROP or key_.replace("_", " ") in DROP:
        return ""
    fn = HANDLERS.get(key_)
    if fn is None:
        return None
    return fn(pos, named, ctx)
