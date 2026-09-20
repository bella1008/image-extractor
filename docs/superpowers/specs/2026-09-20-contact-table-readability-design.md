# Contact table and review readability design

## Scope

Improve the tagged-PDF XML review path without changing source text or preserving arbitrary PDF wrapping. The change covers four reviewed display defects:

1. mark a cover contact title as strong only when the title is typographically stronger than its following explanation;
2. preserve separate source paragraphs inside cover contact-table cells as HTML line breaks;
3. allow the existing validated inline-icon evidence to participate in sentence-break detection for every buyer profile;
4. preserve model-code rows in specification cells only when geometry and token shape prove that every physical line is a model-code list.

It also adds a consolidated pending-review HTML index with per-language displayed-heading, review-unit, table, and figure counts.

## Cover contact classification

A section is a cover contact section only when all of the following are true:

- it has three direct structural children: a nonempty inline title paragraph, a nonempty inline explanation paragraph, and a paragraph that contains exactly one table;
- the table has at least two rows and two or three columns in its first row;
- body cells contain at least one Samsung website URL and at least one numeric contact value outside the URL column;
- table rows contain only reviewed table cells and inline paragraph content.

The classifier does not use translated headings or buyer/language strings. Verified ASIA, MENA, SQ MI, XH, and ZG samples provide the positive fixtures. Safety, regulatory, specification, and disposal tables provide negative coverage.

The table receives `review-table=source-spans` and `review-table-kind=cover-contact`. Existing span geometry remains authoritative. The Markdown writer inserts `<br>` only between distinct paragraph children inside cells of a `cover-contact` table. It does not convert visual wrapping within one paragraph into line breaks.

The title receives a `strong_label` display hint only when complete typography evidence shows a greater font weight than the explanation and a font size no smaller than the explanation. Missing or ambiguous evidence produces no hint.

## Sentence readability

Inline icon detection is already based on geometry, adjacent text, and navigation-route evidence. Sentence detection will use those validated icon paths for all profiles. This lets a paragraph such as `The screen dims.` followed by a navigation sentence retain its sentence break while keeping the existing URL, abbreviation, token, and ambiguous-figure rejection rules.

## Model-code source lines

A table-cell paragraph receives model-row display metadata only when it has at least two distinct baselines with usable bounding boxes and every visible token is an uppercase Latin model token containing both letters and digits. Optional wildcard characters and a final closing parenthesis are allowed. Prose, dimensions, units, lowercase text, incomplete geometry, and mixed-content cells fail closed.

The semantic XML records the reviewed line-start child indexes. The Markdown writer validates those indexes against the direct text children and renders review-only `<br>` boundaries. Source text, raw XML, and token order remain unchanged.

## Review index

A reusable renderer reads each current `review_document.json` and emits one row per buyer/language with displayed headings, review units, semantic tables, and semantic figures. Labels explain that figure counts are XML figure nodes rather than unique image files. The index links to each buyer review page and full semantic preview.

## Verification

Add focused unit and integration tests first, confirm they fail, then implement. Re-extract MENA into a new output folder and compare source PDF, semantic XML, Markdown, and HTML. Run representative contact-table regressions for ASIA, ZG, XH, SQ MI, and non-contact tables; run sentence-break regressions for MENA plus already verified buyers; run the full POC suite, public-import compatibility tests, and compileall.
