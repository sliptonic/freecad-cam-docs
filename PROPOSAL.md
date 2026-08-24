# What this experiment evaluates

FreeCAD's user documentation is a single, rolling MediaWiki. It cannot say which FreeCAD version a
page describes, cannot be reviewed before publication, cannot travel with a code change, and carries
its translations as parallel copies kept in step by hand. 

A page-by-page audit of the CAM workbench documentation against FreeCAD `main` (August 2026) 
found 1,125 needed changes across 92 pages and 13 pages that are linked but do not exist. While
CAM has gotten a lot of work during the 26.3 development cycle, it's clear from the gap that wiki 
documentation isn't keeping pace.

This repository tries an alternative on one workbench, without touching the wiki or any FreeCAD
repository. The design is deliberately unoriginal: it is the pipeline KiCad has run for about ten
years (AsciiDoc sources, Asciidoctor, po4a for translation, one git branch per release, CC BY
content), with the two parts KiCad had to hand-build or do without replaced by maintained tools —
[Antora](https://antora.org/) assembles the versioned site, and CI publishes a preview for every
pull request. FreeCAD's one-page-per-command model is kept rather than adopting KiCAD's single
document model.

## What it should demonstrate

1. **Version fidelity** — the site root shows the imported wiki snapshot; `DEV` is labelled
   pre-release and documents 26.3dev behavior the snapshot does not have.
2. **Independent evolution** — a documentation fix can be applied to one version without changing the
   other.
3. **Information architecture** — the `DEV` navigation covers every CAM command on `main`, and the
   rewritten showcase pages are easier to navigate and understand than the imported ones.
4. **Documentation with code** — a pull request produces a preview URL, the build fails on a broken
   link, and a page can be sourced from a FreeCAD source-tree branch.
5. **Translation readiness** — gettext extraction runs over the sources so translation can use the
   project's existing platform.

Two layouts are under evaluation and neither is preferred yet: documentation in a repository of its
own (this one), or documentation inside the FreeCAD source tree (`src/Mod/CAM/docs/`) aggregated by
the same site build.

## What it is not

Not a proposal to migrate the whole wiki, not a FreeCAD decision, and not connected to the FreeCAD
release process. If the experiment is convincing it will be written up as a FreeCAD Enhancement
Proposal with this repository as the reference implementation.

## Showcase pages

CAM Workbench · Job · Tool Controller · Adaptive · Profile · Pocket · Toolbit Library Manager ·
Post Process — each exists in both versions, and Drilling shows a real behavioral divergence between
1.1 and 26.3dev (the Tapping operation became a `Strategy` of Drilling).

The Audit version shows all the flagged content changes mechanically applied.  This is a starting point
for more human-centric review and edit of the content in preparation for release.

## Decisions

### ASCIIDOC rather than markdown

The choice of AsciiDoc over Markdown follows KiCad's reasoning, and it is a translation and structure 
decision more than a syntax preference. Documentation of this shape needs facilities Markdown does not 
standardize: include:: for shared definitions and generated property tables, document attributes for values 
that vary by version, conditional text, real tables, and admonitions — in Markdown each of these is a 
dialect-specific extension chosen by the site generator, so the content becomes coupled to the tool that 
renders it. 

The decisive factor is translation: po4a's AsciiDoc module has extracted gettext strings from 
KiCad's manuals across twelve languages for a decade, giving translators per-sentence change tracking through 
the same .po workflow FreeCAD's Crowdin already handles, while Markdown's po4a support is weaker and fragments 
across dialects. 

Conversion cost does not separate the two — pandoc emits either from the wiki's MediaWiki 
markup — and the contributor-familiarity argument for Markdown is blunted by the fact that today's authors write 
MediaWiki markup, so any migration asks them to learn a new syntax once. Markdown remains the right choice where 
the project already uses it — the Hugo website and lens-docs are untouched by this decision — but for versioned, 
translated, per-command reference documentation, AsciiDoc is the format with the proven pipeline behind it.
