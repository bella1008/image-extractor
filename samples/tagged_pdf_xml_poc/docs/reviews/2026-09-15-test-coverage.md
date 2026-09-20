# Test coverage measurement — 2026-09-15

Scope: the authorized `feature/xml-markdown-review` worktree only. This does not measure other branches/worktrees.

Coverage.py 7.16.1 was installed in the XML POC virtual environment for measurement. No production dependencies, app behavior, database or coverage threshold were changed.

Two source roots are measured separately and combined with statement/branch counts as weights (not the arithmetic mean of percentages):

- Repository `src`: existing extraction/export/profile code, all 13 Python source files, tested with root `tests` (62 passed).
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor`: current XML pipeline, all source modules, tested with its complete `tests` suite.

Test files, review scripts, PDF samples and metadata/DB data are excluded from the denominator. `src/test.py` is included because it is inside the measured source root; it is not silently omitted.

Line coverage = executed executable statements / all executable statements. Branch coverage = executed branch destinations / all branch destinations. Coverage.py's combined percentage weighs statements and branches together; it is not the same as line coverage.

A high percentage does not prove extraction correctness, complete input coverage, or meaningful assertions. PDF/crop comparisons, structural gates and regression byte checks remain separate evidence.

## Commands

Root: system Python with the POC virtual-environment site-packages exposed for the coverage tool, `coverage run --branch --source=src ... -m pytest tests -q`.

XML POC: `.venv/Scripts/python.exe -m coverage run --branch --source=src/tagged_pdf_extractor --data-file=outputs/coverage_xml_20260915.data -m pytest tests -q`.

The two data files are combined with `coverage combine --keep`; JSON and HTML reports retain per-file missing lines/branches.

## Results

| Scope | Files | Executed / executable lines | Line coverage | Covered / total branches | Branch coverage | Combined |
|---|---:|---:|---:|---:|---:|---:|
| xml | 58 | 7,621 / 7,954 | 95.81% | 3,234 / 3,542 | 91.30% | 94.42% |
| root | 13 | 1,864 / 2,713 | 68.71% | 639 / 1,090 | 58.62% | 65.82% |
| combined | 71 | 9,485 / 10,667 | 88.92% | 3,873 / 4,632 | 83.61% | 87.31% |

XML suite: **2,264 passed, 1 skipped** in 1,353.39 seconds with branch instrumentation. Root suite: **62 passed**. The skip is the Windows symlink capability case, not a PDF/language skip.

HTML: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/coverage_20260915_review/html/index.html`. Raw counts: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/coverage_20260915_review/summary.json`.

The combined line result is 9,485 / 10,667 = 88.92%; the combined branch result is 3,873 / 4,632 = 83.61%. XML-only coverage is higher than the combined result because the older root code is less thoroughly exercised.
