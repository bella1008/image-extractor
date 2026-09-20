# PY / SQ MI XML Review Implementation Plan

> **For agentic workers:** Use subagent-driven-development for independent source review and profile implementation; primary agent owns integration and final validation.

**Goal:** Extract and source-verify PY_ENRU and SQ MI_HEAR through the current XML pipeline, keeping all human approvals pending.

**Architecture:** Source-bound profile modules under samples/tagged_pdf_xml_poc; retain raw tree and per-fragment provenance. Shared reader/application/writer changes are explicit dispatch only. No GridCell/root/DB changes.

**Tech Stack:** pypdf, PyMuPDF, semantic XML/Markdown, local browser rendering, pytest.

Worktree C:/Users/bella/image-extractor/.worktrees/xml-markdown-review; feature/xml-markdown-review.
Initial HEAD bd4fca7264166040b25766a1dce1f67ee7e1415d, clean tree.
MENA/XL/XT/TK/ZW remain pending human approval; no confirmation inferred from this rollout.

- [x] Read project instructions/context; locate PDF filename/profile metadata and record initial state.
- [x] Run existing extractor before edits for both exact sources; inspect PDF pages and output defects.
- [x] PY: verify ENG against ZC first, then RUS against own ENG and CE RUS. Use dedicated domain/py_sheet.py, optional infrastructure/py_source_evidence.py and tests/test_py_*.py.
- [x] SQ MI: no ENG present. Compare ARA with verified MENA/TK ARA and source layout; compare HEB with own ARA. Use dedicated domain/sq_mi_sheet.py, optional infrastructure/sq_mi_source_evidence.py and tests/test_sq_mi_*.py. Do not invent translated headings.
- [x] Source review all cover regions, contact headers/data, safety/image cells, navigation, model/spec units and list/paragraph ownership. Write regressions before minimal fixes.
- [x] Primary wires profile reader/application, then freezes runtime before fresh final extraction. Build review_document/review_run, XML/MD/HTML fidelity proofs and crop comparisons with source differences explicitly recorded.
- [x] Independent source/code review; clear all hard blockers, preserve original wording/non-text warnings. Keep approval pending.
- [x] Focused and full tests, writer/public compatibility, representative regression and compileall; local verified commit only, no push.
- [x] Provide two-buyer HTML review entry and unchanged five-buyer pending links, updated TODO and detailed verification record.

Sources: samples/SUG_RAW/TV_PY/BN68-26639A-00_SUG_Y26 TV ALL_PY_ENRU_260427.0.pdf (A2 RUS/ENG), samples/SUG_RAW/TV_SQ_MI/BN68-24437H-00_SUG_Y26 TV ALL_SQ MI_HEAR_260220.0.pdf (A2 HEB/ARA). Copies in main checkout are byte-identical. No bookmarks in either two-page sheet.
