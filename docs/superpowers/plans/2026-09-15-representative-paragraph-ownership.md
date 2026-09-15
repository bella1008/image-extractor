# Representative paragraph ownership implementation plan

Approved scope: ZC/CE/AFRICA/ZG focused review, XU A3 fee conditions,
KR/LATIN automated regression. TK is the next buyer phase.

Start: feature/xml-markdown-review, c3a497358124eaab6538d799c72c66986af72a8c,
clean worktree. Work only in this worktree; use new output directories.

Goal: clear the eight source-proven ownership defects while retaining every
source fragment, source path, heading, table, and established RTL reading order.

Architecture: XML POC domain repair before path-based display hints are built.
Select exact PDF-observed anchors by source_token/doc_type/canonical language.
Preserve raw_children and original source paths. Keep generic geometry detection
conservative. CE's already verified repair remains a regression control.

- [x] Run current extraction for seven representatives and record profiles,
  bookmark order, input hashes, and output paths in a new before folder.
- [x] Add actual-PDF tests in tests/test_representative_paragraph_ownership.py:
  ZC C-FRA / AFRICA ARA power continuation has a list_body/list_item parent;
  ZG five languages / XU ENG fee paragraphs share a two-item list under the intro.
  Run with `.venv/Scripts/python.exe -m pytest tests/test_representative_paragraph_ownership.py -q`
  and record eight expected failures before runtime edits.
- [x] Add verified_paragraph_source.py with exact extracted anchors and
  verified_paragraph_ownership.py with explicit scope, sibling, role, page,
  language and text guards. Wire before heading promotion in extract_document.py.
  Add negative scope/context and idempotence tests; confirm focused tests pass.
- [x] Extract seven representatives into a new final folder. Compare original
  fragments and non-whitespace character sequences per fragment, heading/table
  signatures, unaffected XML/Markdown, and all 31 existing ownership relations.
  Render corrected Markdown and inspect PDF crop/HTML pairs, including Arabic.
- [x] Run relevant real-PDF regressions, XML/Markdown writer tests, full POC suite,
  three legacy public imports, and compileall for existing required directories.
- [x] Request independent code review; resolve findings. Record counts, scoped
  hard gate results, warnings, evidence and changed files in a review document.
- [x] Update TODO.md and commit verified changes locally. Report full commit hash.

No new buyer-wide approval is implied by this targeted ownership review.
