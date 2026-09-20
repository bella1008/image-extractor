# UA / XD XML extraction review plan

**Goal:** Source-verify UA_ENG and XD_INS with the current XML extractor; leave all approvals pending.

**Architecture:** Existing tagged PDF XML pipeline, isolated source-bound profile modules if defects are proven. Keep source fragments, raw tree, original paths and diagnostic evidence. Reuse current Markdown/HTML review bundle and strictly validate its text and structure. No GridCell, DB, root app or other worktree changes.

**Tech Stack:** POC Python venv, pypdf/PyMuPDF, pytest, local Playwright/Edge.

User has approved this established rollout workflow including autonomous minimal corrections and local commit. Parallel independent UA and XD source review follows dispatching-parallel-agents. Parent owns shared integration, renderer, final verification and commit.

Worktree: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review`; branch `feature/xml-markdown-review`; starting HEAD `d05b4a852c69bd70042d2a65c8c867f6d0d2f573`; initial tree clean.

## Tasks

- [x] Read AGENTS/README/TODO/SUG_RAW_ANALYSIS and canonical profiles. Confirm filenames and actual 2-page A3, no bookmarks: UA_ENG ENG and XD_INS INS.
- [x] Run unmodified extractor into `samples/tagged_pdf_xml_poc/outputs/xml_review_ua_xd_20260919_before`; record branch/head/clean state/source hashes/pages in initial_state.json. Both initial automatic reports pass, pending source review.
- [x] UA source audit: compare ENG to ZC first, then closest XL/XU A3. Inspect all cover regions, contact headers/data, safety symbols, UI, model/spec values, order and paragraph/list relationships. Agent owns domain/ua_sheet.py, optional infrastructure/ua_source_evidence.py, tests/test_ua_sheet.py if needed.
- [x] XD source audit: source-first INS review with closest verified A3 ENG structure as reference, retaining genuine country/wording differences. Agent owns domain/xd_sheet.py, optional infrastructure/xd_source_evidence.py, tests/test_xd_sheet.py if needed. No invented localized headings.
- [x] Reproduce each proven defect in a failing test, add minimal exact-token/type/language/SHA guarded correction. Parent wires only actual required reader/application paths and reviews guards/raw preservation.
- [x] Freeze runtime; extract fresh final folders with scripts/review_ua_xd.py. Extend scripts/review_sheet_rollout.py only for source-verified crop targets. Render MD/HTML and PDF comparison with existing render_representative_review.cjs / render_tk_source_checks.cjs. Confirm artifacts and source audits have matching hashes.
- [x] Verify source inventory/reading order/headings/structured block ownership/contact spans/model quantities. Hard gate must be zero; distinguish source editorial and image warnings from extraction defects. Independent review of changes before accepting.
- [x] Run focused profile tests, writer tests, related/full XML regression as warranted, root public imports/tests and compileall. Re-extract representative existing profiles and compare XML/MD bytes. Preserve previous outputs.
- [x] Write final review.html, detailed docs/reviews/2026-09-19-ua-xd-xml-review.md and TODO; final source approval false. Existing pending 7 remain MENA/XL/XT/TK/ZW/PY/SQ_MI; UA/XD become 9 only after extraction passes. Local verified commit, no push.

Sources under worktree samples/SUG_RAW:
- TV_UA/BN68-26754A-00_SUG_Y26 TV ALL_UA_ENG_260520.0.pdf — SHA256 38b9bdb357c6b9fd0ccfa0fc3fd3e3a0a0c9ce787fe56fb3fc16c4db1c1ee80a.
- TV_XD/BN68-25031D-00_SUG_Y26 TV ALL_XD_INS_260113.0.pdf — SHA256 f332cca0f65ea88a6b00489d076173a6a5eaf859bc4a1773c05a3153c97dad56.
