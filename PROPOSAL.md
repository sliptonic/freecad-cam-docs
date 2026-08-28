# What this experiment evaluates

FreeCAD's user documentation is a single, rolling MediaWiki. It cannot say which FreeCAD version a
page describes, cannot be reviewed before publication, cannot travel with a code change, and carries
its translations as parallel copies kept in step by hand. A page-by-page audit of the CAM workbench
documentation against FreeCAD `main` (August 2026) found 1,125 needed changes across 92 pages and 13
pages that are linked but do not exist.

This repository tries an alternative on one workbench, without touching the wiki or any FreeCAD
repository. The design is deliberately unoriginal: it is the pipeline KiCad has run for about ten
years (AsciiDoc sources, Asciidoctor, po4a for translation, one git branch per release, CC BY
content), with the two parts KiCad had to hand-build or do without replaced by maintained tools —
[Antora](https://antora.org/) assembles the versioned site, and CI publishes a preview for every
pull request. FreeCAD's one-page-per-command model is kept.

## What it should demonstrate

1. **Version fidelity** — the site root shows the imported wiki snapshot; `DEV` is labelled
   pre-release and documents 26.3dev behavior the snapshot does not have.
2. **Independent evolution** — a documentation fix can land on one version without changing the
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

## Decisions that have to come first

The CAM import works, and a second workbench went through the same tooling cleanly — Sketcher's 128
pages converted with no unresolved links and no hand-editing. That says the machinery generalizes.
It says nothing about the questions below, which are the ones people have to answer. Most get
harder to reverse the longer they wait, because every file that exists and every link that points at
it has to be moved again. The first and the sixth decide the shape of everything else.

**1. How much of the wiki is in scope?**
The wiki has about 2,500 English pages. CAM is 60 of them; Sketcher is another 128. Converting one
workbench is a weekend of work. Converting all of it is a different project, with different owners
and a much longer timeline. Every decision below reads differently depending on this answer.

**2. One book, or one book per workbench?**
Today the CAM documentation is a self-contained site. If more of the wiki moves, either it all
becomes one large book or each workbench gets its own with links between them. The Sketcher import
gives a useful measurement here. Of the links that leave the workbench, only about a fifth go to
another workbench. Two thirds point at general pages that belong to nobody in particular — things
like *Expressions* or *Feature editing*. So either shape needs a shared section for the pages
everyone relies on, and that shared section is also where most of the wiki's unsorted pages live.
It is the biggest unclaimed pile in the whole corpus.

**3. Where do the files live?**
The two layouts named above — a documentation repository of its own, or documentation inside the
FreeCAD source tree — are still both open. This one is worth settling early. Locations end up
written into links, into translation files, and into people's habits.

**4. What happens to the images?**
The wiki holds about 9,000 image files. CAM needed 185 of them and Sketcher needed 315; all of them
together come to roughly a quarter of a gigabyte, and probably more once the photo-heavy tutorial
pages are counted. Git stores text well and large binary files badly. Keeping the images beside the
text, keeping them somewhere separate, or using Git's large-file support are all workable. Changing
your mind afterwards means rewriting the repository's history.

**5. Do the translations come with it, and when?**
Behind the 2,500 English pages sit about 17,800 translated ones in 28 languages. French, German,
Polish and Italian each cover roughly 2,000 pages. The importer already handles one language at a
time, so this is not a tooling problem. It is a people problem: translators need to keep working
through the move, on a platform they already use. FreeCAD has Crowdin. Agreeing on how the two fit
together belongs before a migration, not after one.

**6. Who gets to edit, and how?**
This is the change contributors will actually feel, and it deserves more attention than any of the
technical questions. Anyone can fix a typo on the wiki right now, in a browser, with no review and
no account beyond a wiki login. Documentation kept in git needs a pull request. In exchange you
get review before publication, a page that can say which FreeCAD version it describes, and a doc
fix that ships alongside the code change that caused it. What you lose is the drive-by correction
from someone who was never going to learn git. Whether that gap gets filled with a web editor, a
simpler contribution path, or an accepted tradeoff is a real decision, not a detail to sort out
later.

**7. What happens to the wiki afterwards?**
If pages move, the wiki has to become something definite: the live copy still, a frozen archive, or
a set of redirects. Leaving two live copies to drift apart is the worst result available, and it is
the one that happens by default when nobody chooses.

**8. Which pages should not come along at all?**
Not everything on the wiki is a manual page. Roughly 240 pages are user-contributed macros, 25 are
chapters of a book, and a couple of dozen are generated code reference. Those are different kinds of
documents with different lifetimes and different authors. Treating them as manual pages would make
all of them worse, so some of the wiki should probably stay a wiki.

## Showcase pages

CAM Workbench · Job · Tool Controller · Adaptive · Profile · Pocket · Toolbit Library Manager ·
Post Process — each exists in both versions, and Drilling shows a real behavioral divergence between
1.1 and 26.3dev (the Tapping operation became a `Strategy` of Drilling).
