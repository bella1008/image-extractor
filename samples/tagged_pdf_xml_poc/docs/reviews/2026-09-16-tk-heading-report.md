# TK ARA heading report correction

User observed `01`–`05` as `10`–`50` with spaces between digits in the heading correspondence table.

The semantic XML already contains verified `numbered-label="01"` etc. The Markdown writer validates the original split label fragments and compacts their display. Markdown and the full preview were correct. The report generator instead used `_element_text`, producing `0 1`, which separates the digits into distinct runs in an RTL cell.

`review_tk_xml.heading_display_text` now reuses the writer's source-label validation and compact numbered label. `render_tk_review.cjs` isolates that verified number with `<bdi dir="ltr">01</bdi>`. It does not reverse text or infer a number from the row position.

New output: `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review/samples/tagged_pdf_xml_poc/outputs/xml_review_tk_20260916_heading_review/tk_review.html`.

The refresh script copies the accepted bundle into a new directory, preserving all source findings/crops and updates only heading report metadata. Both PDFs' raw XML, semantic XML, Markdown, extraction report and complete preview (10 files) remain byte-identical. Only five ARA heading display strings change; no extractor/runtime modules change.

Verification:

- Eight new regressions failed before implementation, then passed.
- Heading report + TK writer evidence + Markdown writer: **294 passed**.
- Browser: all **72** ENG/TUR/ARA table headings match complete MD previews.
- Browser: five labels are `01`, `02`, `03`, `04`, `05`, have LTR isolation, digit zero is left of the second digit, and no inserted whitespace/gap.
- `heading_display_validation.json` and five heading screenshots are in the new output folder.
- POC `compileall src tests scripts` and root `compileall src tests` passed; root scripts/apps and POC apps do not exist.

Start branch `feature/xml-markdown-review`; start HEAD `248547f1f901182e637c92d833c4b7186de7f15a`; initial working tree clean. Local recovery commit is recorded in the final review_run files and completion response.
