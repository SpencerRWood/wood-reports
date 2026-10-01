# Portable LaTeX workspaces

Publish a compiled report with `LatexWorkspacePublisher().publish(report,
workspace, artifact_root=chart_directory)`. The returned entrypoint remains
`generated/report.tex`. The workspace is a reproducible source artifact; the
compiled PDF is the client deliverable.

The publisher writes generated source, copied chart assets, and
`generated/workspace.json`. This deterministic manifest records the workspace
entrypoint, document/profile metadata, complete publication theme, ownership
directories, SHA-256 source fingerprints, preferred engine, and build arguments.
Chart dependencies use relative paths and safe filenames. No source artifact
directory is needed after publication. The bundled Wood Analytics typography
uses available font fallbacks; identical PDF bytes across different font or TeX
installations are not promised.

Run the manifest's build command from its `working_directory`, relative to the
workspace root. The default is:

```sh
cd generated
lualatex -no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=build report.tex
lualatex -no-shell-escape -interaction=nonstopmode -halt-on-error -output-directory=build report.tex
```

Two passes resolve cross-references. The publisher creates `generated/build`;
its disposable compiler outputs are excluded from source fingerprints. This
story supplies source and build metadata, without provisioning a compiler service.

## Ownership and human extensions

The publisher replaces its generated tree on regeneration. It refuses to replace
modified or unrecognized source trees, including added source files and symlinks.
Move intentional edits out of that tree before regenerating. To migrate an older
workspace without a manifest, move the old generated directory aside first.
The publisher does not create or modify the human-maintained `extensions` tree.
Optional `extensions/preamble.tex` and `extensions/body.tex` are included before
the document and at its end, respectively. These are trusted human TeX extensions;
their dependencies must also be portable. Keep extension files with the workspace
when moving it. Customize directory names with the publisher's constructor;
names must contain only letters, digits, underscores, and hyphens.

## Text, labels, and references

Ordinary narrative, metadata, captions, tables, and source notes are escaped as
text. Markdown emphasis, links, lists, and code retain their publication semantics.
Appendices use native LaTeX appendix sections.

Programmatic renderer hints support `latex.label` on sections, appendices, charts,
and tables. Labels use a letter followed by letters, digits, colons, underscores,
periods, or hyphens, and must be unique within a report. A narrative with
`latex.ref` renders its escaped text followed by a numbered reference. References
may point forward; missing targets fail generation. Figures also receive generated
labels; finding visuals default to labels based on the finding identity. A labeled
table receives a caption counter even when its caption text is absent.
`latex.source` on charts and tables adds an escaped source note; table notes and
captions remain independent.

Raw TeX is an explicit programmatic opt-in with a narrative's
`renderer_hints={"latex.raw": "inline"}`. It permits at most 4096 characters with
balanced, nested `\textbf{}`, `\textit{}`, `\emph{}`, and `\texttt{}` commands.
Other commands, standalone braces, TeX special characters, and newlines are
rejected. This mode does not allow file input, definitions, or shell commands.
Markdown authors do not need to write TeX.
