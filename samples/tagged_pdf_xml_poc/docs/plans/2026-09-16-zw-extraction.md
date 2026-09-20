# ZW XML extraction review

Source: BN68-24973D-00_SUG_Y26 TV ALL_ZW_TPE_260327.0.pdf.
Profile: ZW_TPE / A3 / TPE, two pages, no bookmarks.
Initial branch: feature/xml-markdown-review; HEAD e06b998844e3b09887e612f4f22940abffeac2a4; clean worktree.

1. Baseline extraction before edits (done): outputs/xml_review_zw_20260916_before.
2. Verify both source pages and cover, safety, specifications, navigation and RoHS crops.
3. Add failing tests for observed overprint duplication, paragraph ownership, cover ordering and source object evidence. Implement exact-profile repairs with raw evidence retained.
4. Extract into a fresh directory, compare source/XML/Markdown/HTML and record all exceptions and editorial source findings.
5. Run focused, writer/public compatibility and representative buyer regression checks, full relevant suite and compileall. Commit only verified changes locally.

No checklist DB, GridCell, other worktrees, item-review or Excel/app changes. Unknown source revisions must not inherit source-pinned exceptions. No invented localized text.
