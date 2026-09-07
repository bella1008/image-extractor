# Cross-Buyer Inline Icon Detection Design

## Status

Approved direction from the 2026-09-07 review. This document defines the implementation boundary for the next change in `samples/tagged_pdf_xml_poc`.

## Problem

The current detector classifies an empty tagged `Figure` as `[아이콘]` only when its BBox is small relative to the font sizes of the immediately adjacent text fragments. This works for many inline figures, but it misses real OSD navigation icons when the PDF reports an anomalous adjacent font size such as `1.0 pt`. The same 9 x 9 figure can therefore be classified differently inside one navigation path.

The rule must work across buyers, layouts, and languages. It must not depend on a source token, buyer name, language, translated wording, icon name, or fixed body font size.

## Observed Cross-Buyer Evidence

The generated semantic XML shows the same structural pattern in ZG, ZC, KR, ZA, and XY:

```text
([FIGURE] > direction text > [FIGURE] Settings > Support > ...)
```

The words vary by language, but the tagged figure placement and repeated `>` separators remain stable. Parentheses are common but cannot be mandatory because some navigation paths begin directly with an icon. Parentheses alone are not sufficient evidence because ordinary prose and image captions can also contain them.

Measured review evidence from the current artifacts:

- ZG: 100 figures occur in flows containing repeated `>` navigation syntax; 35 are missed by the current adjacent-font rule.
- ZC: 20 such figures; 15 are missed.
- KR: 16 such figures; 13 are missed.
- ZA and XY artifacts contain the same route topology, although those artifacts predate the current icon annotation pass.

Some ZG route figures are approximately 24 x 9 units rather than 9 x 9, so a strict generic width ratio also rejects valid elongated remote-control/button icons.

## Goals

- Recognize OSD/navigation icons using wording-independent structural evidence.
- Preserve a generic fallback for non-navigation inline icons such as wall-anchor and switch symbols.
- Remain conservative for standalone illustrations, safety-symbol tables, product diagrams, and ambiguous figures.
- Preserve auditable detection evidence in semantic XML.
- Apply the same algorithm to all profiles without buyer-specific dispatch.

## Non-Goals

- Naming an icon as Home, Settings, Volume, or another semantic class.
- OCR or image similarity recognition.
- Changing Markdown escaping such as `\[아이콘]:` at the beginning of a block.
- Building the final Excel sentence exporter. Markdown `<br>` remains presentation-only and is not part of this change.

## Considered Approaches

### 1. Punctuation-only classification

Classify every figure in a paragraph containing `>`, `(`, or `)` as an icon.

Rejected because the punctuation may be unrelated to a particular figure, parentheses are common in prose, and this approach gives no geometric protection against embedded illustrations.

### 2. Expand the current size limits

Keep adjacent-font classification and increase the width and height ratios.

Rejected because malformed adjacent font metadata remains the root cause. Larger global limits would also increase false positives for non-icon figures.

### 3. Two-path structural and relative-geometry classifier

Selected. Use a high-confidence navigation-route path and retain a stricter generic-inline path. Both paths share mandatory source-integrity checks.

## Selected Design

### Common mandatory checks

A figure can be considered only when all of the following hold:

- It is inside an eligible inline `paragraph` or `list_body` flow, including the existing `span` and `link` wrappers.
- It has no visible extracted text or visible `ActualText` descendant.
- It has one unambiguous, positive, finite BBox.
- Its page index is valid.
- Supporting visible text is on the same page.
- A structural barrier such as a table, heading, caption, label, nested list, or standalone figure separates independent flows.

Failure of any mandatory check leaves the node as a generic figure.

### Path A: navigation-route icon

Build a local token window around each candidate figure from the existing inline flow. A candidate has strong navigation-route evidence when:

1. Either the nearest visible token on at least one side begins or ends with the ASCII `>` separator after whitespace normalization, or the figure is immediately followed by a balanced non-empty parenthesized control label before the first `>` separator.
2. The contiguous flow segment contains at least two `>` separators and at least one visible non-punctuation text token.
3. No structural barrier or page transition occurs inside that segment.

Balanced `(` and `)` surrounding the segment increase confidence and are serialized as audit evidence. A balanced control label immediately after a candidate also supplies local adjacency evidence for layouts such as `figure (control label) > action > action`. Parentheses are not otherwise required, and a single parenthesis or a single `>` is never enough.

The detector must inspect a candidate-local sentence window, not merely ask whether the entire parent paragraph contains `>`. Sentence terminals bound that window. A terminal immediately followed by a route separator is retained inside the route, as is a period after a short abbreviation followed by a lowercase continuation. Closing punctuation between that terminal and the separator is ignored. This prevents an unrelated comparison symbol in a later sentence from classifying the figure while preserving abbreviated control labels such as `Aum. vol.`.

For this path, font size is a secondary sanity check rather than the deciding signal. Valid same-page styles in the candidate-local window are filtered symmetrically in log-size space using the median absolute deviation, then reduced to a visible-character-weighted median. This prevents either one anomalously small fragment or one anomalously large glyph from dominating the reference. The route path uses a distinct, wider relative-width allowance for elongated inline button icons while retaining a conservative relative-height limit. The initial tested limits are:

- maximum width/reference-font ratio: `5.0`
- maximum height/reference-font ratio: `2.5`

If a reliable segment reference font cannot be calculated, the candidate remains a generic figure. No absolute point-size fallback is introduced.

### Path B: generic inline icon

For figures without strong navigation-route evidence, retain the existing conservative classification:

- visible text immediately adjacent on at least one side;
- same-page evidence;
- maximum width/reference-font ratio `3.0`;
- maximum height/reference-font ratio `2.0`.

Improve the reference font calculation by using valid visible text across the candidate's contiguous inline segment. Immediate neighbors remain evidence that the figure is inline, but a malformed neighbor does not become the sole reference size.

This path covers icons such as wall-anchor, switch, and short inline legend symbols without relying on their wording.

### Detection reason and XML evidence

`InlineIconHint.reason` must distinguish the paths:

- `navigation_route_inline_figure`
- `small_inline_figure_with_adjacent_text`

Semantic XML continues to record BBox, reference font size, and width/height ratios. Navigation-route hints additionally record the separator count and whether balanced surrounding parentheses were observed. Markdown renders both accepted reasons as the same neutral `[아이콘]` token. It does not infer an icon name.

The Markdown reader validates each reason against its own allowed ratio limits and verifies that serialized evidence agrees with a fresh domain-level detection pass. Unknown reasons or contradictory evidence fail output publication.

## Data Flow

```text
tagged structure
  -> inline flow tokens
  -> common source-integrity checks
  -> local navigation-route evidence
       -> Path A relative-geometry sanity check
     otherwise
       -> Path B generic relative-geometry check
  -> InlineIconHint with reason and evidence
  -> semantic XML display attributes
  -> Markdown [아이콘] or generic figure fallback
```

The raw tagged structure and source text are not rewritten.

## Error Handling and Conservative Fallback

- Missing, conflicting, malformed, or non-finite BBox: generic figure.
- Missing or inconsistent text style evidence: generic figure.
- Figure text/ActualText present: generic figure, because text recovery takes priority.
- One separator only, unbalanced punctuation without a repeated route, or a distant unrelated `>`: generic path only.
- Any disagreement between domain detection, XML evidence, and Markdown validation: fail publication rather than silently change the classification.

## Verification

### Unit tests

- Detect first, middle, and final icons in parenthesized and non-parenthesized navigation paths.
- Detect navigation routes in language-independent text fixtures.
- Confirm that one `>`, ordinary parentheses, mathematical/comparison prose, and distant separators do not trigger Path A.
- Confirm that a `1.0 pt` adjacent outlier does not override the route segment's dominant font size.
- Accept tested 9 x 9 and 24 x 9 route icons within the Path A limits.
- Reject figures beyond the route height/width limits.
- Preserve generic wall-anchor-style icon behavior through Path B.
- Reject standalone figures, table/safety figures, cross-page evidence, visible figure text, and malformed attributes.
- Round-trip both reasons and their evidence through XML and Markdown validation.

### Real-PDF regression

- Automated extraction/regression: ZG, ZC, KR, ZA, and XY.
- Human Markdown/PDF spot review: ZG, ZC, and KR, matching the current review scope.
- Confirm that previously accepted sentence breaks, special characters, headings, lists, tables, RF formatting, and DoC formatting do not change.
- Confirm that icon counts in the semantic model, semantic XML, and Markdown remain identical.
- Confirm that all reports retain `status=pass`.

## Acceptance Criteria

- The questioned ZG OSD figures render as `[아이콘]` consistently within each route.
- Equivalent ZC, KR, ZA, and XY navigation paths are handled by the same code path.
- No source-token, buyer, language, menu-label, translated-text, or absolute-font-size dispatch is added.
- Existing generic inline icons remain detected.
- Ambiguous or standalone images remain `[그림: 텍스트 없음]`.
- Required focused tests, real-PDF regressions, and `python -m compileall src tests` pass.
