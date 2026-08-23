# FreeCAD CAM documentation — experiment

This repository is a personal experiment by one FreeCAD contributor. It is **not** an official
FreeCAD project and does not replace the [FreeCAD wiki](https://wiki.freecad.org/CAM_Workbench).

It publishes the CAM workbench documentation as a versioned site built from git:

- branch `wiki` — the wiki's CAM pages, imported mechanically from MediaWiki markup and labelled
  by import date (the documentation FreeCAD has today, shown in the new pipeline);
- branch `DEV` — a rewrite of the same documentation against FreeCAD `main` (26.3dev), with a new
  information architecture.

The site lets the reader switch between the two. See [PROPOSAL.md](PROPOSAL.md) for what the
experiment is trying to show and why.

Site: https://sliptonic.github.io/freecad-cam-docs/

## Layout

```
antora.yml                 component descriptor (differs per branch)
antora-playbook.yml        site assembly: which branches become which versions
modules/ROOT/              pages, navigation, images, partials (Antora standard layout)
supplemental-ui/           header override that puts the version selector in the header
tools/                     wiki importer, template handlers, migration report, helpers
.github/workflows/         build, validate, deploy, pull-request previews
```

## Build locally

```
npm ci
npx antora antora-playbook.yml        # output in build/site/
```

`antora-playbook.yml` reads the `wiki` and `DEV` branches of this clone, so both must exist
locally (`git branch wiki origin/wiki`).

To re-run the wiki import (branch `wiki` only) you need `pandoc` and a clone of the wiki bridge
repository:

```
python3 tools/import_wiki.py --source ../FreeCAD-Documentation-Project/wiki --out modules/ROOT
```

## Licenses

- Documentation content on the `wiki` branch is imported from the FreeCAD wiki and is licensed
  [CC BY 3.0](LICENSE-CONTENT), © the FreeCAD wiki contributors. Rewritten content on `DEV` is
  CC BY 3.0 as well.
- Tooling (`tools/`, CI, UI overrides) is [LGPL-2.1-or-later](LICENSE).
