# Checklist UI run implementation plan

Goal: connect the approved local PDF execution flow to the existing combined viewer.
Architecture: input preparation validates paths/environment; Streamlit calls the shared workflow and reads its checked completion.
Tech stack: Python, Streamlit AppTest, existing XML extractor and workbook service.

- [x] Add UI tests for successful real service linkage, failure clearing, repeat-run isolation and invalid inputs; run them before implementation.
- [x] Add src/combined_review_input.py for request construction and unique output naming.
- [x] Connect scripts/combined_review_app.py to run_combined_review and auto-load only completed output.
- [x] Include XML package path in scripts/start_item_review_ui.py subprocess environment, only for --combined.
- [x] Run focused combined workflow/UI tests: 58 passed. compileall src tests scripts passed; apps absent in this worktree.
- [x] Exercise real ZC PDF through AppTest; document actual outcome and output meaning in migration guide, README and TODO.

Use existing tests/test_combined_review_ui.py and tests/test_combined_review_run.py. Tests use checked_bundle
and the existing test workbook builder to isolate expensive IO while retaining real observers and completion validation.
Do not alter extraction rules or checklist data. Continue in the current isolated worktree under the user's standing authorization.
