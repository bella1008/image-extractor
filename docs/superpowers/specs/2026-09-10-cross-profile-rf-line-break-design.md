# Cross-Profile RF Source Line-Break Design

## Goal

Preserve PDF-authored comma-following line breaks in RF specification table cells
for every profile that exposes the same tagged-PDF evidence. XU must render the
frequency entries with the same reviewer-visible line structure as ZG without
matching buyer names, model names, RF wording, or language text.

## Confirmed Root Cause

The reusable detector already requires an inline `actual-text="\n"` boundary,
a preceding comma, non-empty text on both sides, and a containing table cell.
However, its application is coupled to the ZG-only review-formatting gate that
also enables Declaration-of-Conformity typography formatting.

The XU RF table contains 18 qualifying source newline markers, but none receives
a semantic `preserved-line-break` role because XU does not pass the ZG gate.

## Design

Split the current formatting orchestration into two independently dispatched
behaviors:

1. Apply RF source-line-break detection to all documents. The detector remains
   fail-closed and acts only on complete structural source evidence.
2. Keep form-cluster/Declaration-of-Conformity display hints behind the existing
   verified `ZG XN ZT_L05 + BOOK` scope.

The Markdown writer remains buyer-independent and only renders validated semantic
line-break hints. Raw XML remains unchanged. Semantic XML retains each source
newline and adds `display-role="preserved-line-break"` only when the generic
detector conditions pass.

This is not a generic comma splitter. A comma with no explicit PDF newline, a
newline outside a table cell, or a non-comma newline remains unchanged.

## Compatibility and Safety

- XU: 18 RF source newlines become preserved reviewer line breaks.
- ZG: existing preserved RF line breaks remain unchanged.
- ZC, ZA, XY, KR, and other profiles: no new break is emitted unless their tagged
  structure contains the same qualifying source evidence.
- ZG DoC heading and strong-label rendering remains profile-scoped.
- XU Warranty headings remain source-role headings and are unaffected.
- No source-token, model-name, RF-title, or language dictionary is added.

## Verification

TDD must prove:

- XU-like filenames preserve a qualifying table-cell source newline;
- a qualifying boundary no longer depends on the ZG profile token;
- DoC/form-cluster hints remain disabled outside ZG;
- ordinary commas, non-comma source newlines, and newlines outside table cells do
  not gain preserved-break hints;
- the real XU bundle contains 18 preserved breaks and renders each RF frequency
  item on its source-authored line;
- the real ZG result remains stable;
- focused tests, the complete POC suite, and repository compile checks pass.
