# Numbered Chapter Heading Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote verified `List Item > Label + List Body` chapter structures such as `03 Troubleshooting and Maintenance` to level-2 semantic and Markdown headings using a profile-free combination of number sequence and relative typography.

**Architecture:** Extend the existing MCID text path with parallel font metadata, then run a pure domain promotion pass immediately after PDF reading. The pass detects chapter series at each `01`, validates contiguous numbering and relative font size, and stores auditable promotion records without changing the source tree; raw XML ignores those records, while semantic XML, Markdown, and quality evaluation consume them.

**Tech Stack:** Python 3.11+, pypdf 6.16.2 private text extraction visitor, dataclasses, ElementTree XML, pytest 8.

---

Run all commands from `samples/tagged_pdf_xml_poc` in the isolated `feature/xml-markdown-review` worktree.

## File map

- Modify `src/tagged_pdf_extractor/domain/models.py`: add font-style and promotion audit value objects while preserving existing positional constructors.
- Modify `src/tagged_pdf_extractor/infrastructure/pypdf_operation_text.py`: expose font name and size with every decoded text callback.
- Modify `src/tagged_pdf_extractor/infrastructure/mcid_text.py`: retain text styles alongside MCID text parts.
- Modify `src/tagged_pdf_extractor/infrastructure/pypdf_reader.py`: attach collected styles to `ContentFragment` instances.
- Create `src/tagged_pdf_extractor/domain/numbered_heading_promotion.py`: detect, validate, and audit profile-free chapter series.
- Modify `src/tagged_pdf_extractor/application/extract_document.py`: invoke the promotion pass before quality evaluation and output validation.
- Modify `src/tagged_pdf_extractor/application/evaluate_quality.py`: count accepted promotions as headings and expose series metrics and hard gates.
- Modify `src/tagged_pdf_extractor/infrastructure/xml_writer.py`: keep raw XML unchanged and render accepted promotions as semantic `<heading level="2">` elements with evidence attributes.
- Modify `src/tagged_pdf_extractor/infrastructure/markdown_writer.py`: render semantic headings inside lists as Markdown headings without list markers or duplicate text.
- Modify `tests/test_pypdf_operation_text.py`, `tests/test_mcid_text.py`, `tests/test_pypdf_reader.py`: cover typography transport.
- Create `tests/test_numbered_heading_promotion.py`: cover pure candidate, sequence, series, and typography decisions.
- Modify `tests/test_quality_evaluator.py`, `tests/test_xml_writer.py`, `tests/test_markdown_writer.py`, `tests/test_cli.py`: cover report/output/application integration.
- Modify `tests/test_zc_integration.py` and `tests/test_layout_regression.py`: verify ZC, ZA, and ZG representative PDFs.
- Modify `README.md`: explain the verified numbered-heading rule and new report fields.

### Task 1: Expose font metadata from the pypdf operation runner

**Files:**
- Modify: `src/tagged_pdf_extractor/infrastructure/pypdf_operation_text.py`
- Modify: `tests/test_pypdf_operation_text.py`

- [ ] **Step 1: Write a failing callback metadata test**

Add a focused test using the existing `_in_memory_page` helper:

```python
def test_runner_reports_font_name_and_size_with_text() -> None:
    page = _in_memory_page(b"BT /F1 12 Tf (Heading) Tj ET")
    captured: list[tuple[str, str | None, float | None]] = []

    PypdfOperationTextRunner().run(
        page,
        on_boundary=lambda _operator, _operands: None,
        on_text=lambda value, font_name, font_size: captured.append(
            (value, font_name, font_size)
        ),
    )

    assert captured == [("Heading", "Helvetica", 12.0)]
```

Mechanically update existing test callbacks in this file to accept three arguments. For callbacks that discard metadata, use:

```python
def capture_text(value: str, _font_name: str | None, _font_size: float | None) -> None:
    captured.append(value)
```

- [ ] **Step 2: Run the focused test and verify the interface fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_pypdf_operation_text.py::test_runner_reports_font_name_and_size_with_text -v
```

Expected: FAIL because `on_text` currently receives only the decoded string.

- [ ] **Step 3: Pass normalized font metadata from the pypdf visitor**

Change the callback contract and visitor in `PypdfOperationTextRunner.run`:

```python
on_text: Callable[[str, str | None, float | None], None],
```

```python
def visitor(
    value: str,
    _cm: Any,
    _tm: Any,
    font: Any,
    font_size: Any,
) -> None:
    if not value:
        return
    name = getattr(font, "name", None)
    normalized_name = str(name).lstrip("/") if name is not None else None
    try:
        normalized_size = float(font_size)
    except (TypeError, ValueError, OverflowError):
        normalized_size = None
    if normalized_size is not None and (
        normalized_size <= 0 or not math.isfinite(normalized_size)
    ):
        normalized_size = None
    _invoke_callback(on_text, value, normalized_name, normalized_size)
```

Add `import math`. Do not inspect or hardcode `SamsungOne-*`; the normalized name is evidence only.

- [ ] **Step 4: Run the complete operation-runner test file**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_pypdf_operation_text.py -v
```

Expected: PASS, including callback exception-chain and non-mutating content-stream tests.

- [ ] **Step 5: Commit the runner contract**

```powershell
git add src/tagged_pdf_extractor/infrastructure/pypdf_operation_text.py tests/test_pypdf_operation_text.py
git commit -m "Capture font metadata from PDF text operations"
```

### Task 2: Carry font styles from MCIDs into the domain tree

**Files:**
- Modify: `src/tagged_pdf_extractor/domain/models.py`
- Modify: `src/tagged_pdf_extractor/infrastructure/mcid_text.py`
- Modify: `src/tagged_pdf_extractor/infrastructure/pypdf_reader.py`
- Modify: `tests/test_mcid_text.py`
- Modify: `tests/test_pypdf_reader.py`

- [ ] **Step 1: Write failing MCID and reader tests**

Introduce a metadata-aware `FakeRunner` text event in `tests/test_mcid_text.py`:

```python
elif kind == "text":
    text, font_name, font_size = value
    on_text(text, font_name, font_size)
```

Convert existing fake text events to triples such as `("Settings >", None, None)` and add:

```python
def test_collects_parallel_styles_for_each_mcid_text_part() -> None:
    runner = FakeRunner(
        [
            ("boundary", (b"BDC", ["/P", {"/MCID": 7}])),
            ("text", ("03", "SamsungOne-600", 16.0)),
            ("text", ("Title", "SamsungOne-600", 16.0)),
            ("boundary", (b"EMC", [])),
        ]
    )

    result = McidTextCollector(runner=runner).collect(object(), page_index=0)

    assert result.parts_by_mcid == {7: ("03", "Title")}
    assert result.styles_by_mcid == {
        7: (
            TextStyle(font_name="SamsungOne-600", font_size=16.0),
            TextStyle(font_name="SamsungOne-600", font_size=16.0),
        )
    }
```

Add a reader test asserting a resolved `ContentFragment` receives the styles associated with the same page and MCID and that unresolved/empty fragments receive `text_styles=()`.

- [ ] **Step 2: Run the focused tests and verify missing types/fields**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_mcid_text.py tests/test_pypdf_reader.py -v
```

Expected: FAIL because `TextStyle`, `styles_by_mcid`, and `ContentFragment.text_styles` do not exist.

- [ ] **Step 3: Add backward-compatible style value objects**

In `domain/models.py`, define the style before `ContentFragment` and append the new field after existing fields:

```python
@dataclass(frozen=True)
class TextStyle:
    font_name: str | None
    font_size: float | None


@dataclass(frozen=True)
class ContentFragment:
    page_index: int
    mcid: int | None
    text_parts: tuple[str, ...]
    object_ref: str | None = None
    text_styles: tuple[TextStyle, ...] = ()

    @property
    def text(self) -> str:
        return "".join(self.text_parts)
```

Keeping `text_styles` last preserves all current positional `ContentFragment(page, mcid, parts, object_ref)` calls.

- [ ] **Step 4: Collect parallel text styles per MCID**

Extend `McidTextResult` and `collect`:

```python
@dataclass(frozen=True)
class McidTextResult:
    parts_by_mcid: dict[int, tuple[str, ...]]
    styles_by_mcid: dict[int, tuple[TextStyle, ...]]
    seen_mcids: frozenset[int]
    diagnostics: tuple[Diagnostic, ...]
```

```python
styles: dict[int, list[TextStyle]] = {}

def on_text(
    value: str,
    font_name: str | None,
    font_size: float | None,
) -> None:
    if value and stack and stack[-1] is not None:
        mcid = stack[-1]
        parts.setdefault(mcid, []).append(value)
        styles.setdefault(mcid, []).append(TextStyle(font_name, font_size))
```

Return `styles_by_mcid` with tuples and assert before returning that every styled MCID has the same number of text parts and styles.

- [ ] **Step 5: Attach styles in `TaggedPdfReader`**

Build both page maps in `read`:

```python
mcid_text: dict[int, dict[int, tuple[str, ...]]] = {}
mcid_styles: dict[int, dict[int, tuple[TextStyle, ...]]] = {}
```

Thread `mcid_styles` through `_walk_kids`, `_walk_kid`, and `_content_fragment`, then construct:

```python
return ContentFragment(
    page_index=stored_page_index,
    mcid=mcid,
    text_parts=tuple(text_parts),
    object_ref=reference,
    text_styles=tuple(page_styles.get(mcid, ())) if mcid is not None else (),
)
```

Do not synthesize styles for unresolved MCIDs.

- [ ] **Step 6: Run transport and XML regression tests**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_pypdf_operation_text.py tests/test_mcid_text.py tests/test_pypdf_reader.py tests/test_xml_writer.py -v
```

Expected: PASS; existing XML output is unchanged because style serialization has not yet been enabled.

- [ ] **Step 7: Commit typography transport**

```powershell
git add src/tagged_pdf_extractor/domain/models.py src/tagged_pdf_extractor/infrastructure/mcid_text.py src/tagged_pdf_extractor/infrastructure/pypdf_reader.py tests/test_mcid_text.py tests/test_pypdf_reader.py
git commit -m "Carry MCID typography into content fragments"
```

### Task 3: Implement the pure numbered-heading promotion domain pass

**Files:**
- Modify: `src/tagged_pdf_extractor/domain/models.py`
- Create: `src/tagged_pdf_extractor/domain/numbered_heading_promotion.py`
- Create: `tests/test_numbered_heading_promotion.py`

- [ ] **Step 1: Write candidate-format and direct-child structure tests**

Create synthetic helpers that build real `StructureElement` trees with styled fragments:

```python
def _fragment(text: str, size: float | None, mcid: int) -> ContentFragment:
    return ContentFragment(
        page_index=0,
        mcid=mcid,
        text_parts=(text,),
        text_styles=(TextStyle("TestFont", size),),
    )


def _chapter(
    label: str,
    title: str,
    label_size: float | None = 16.0,
    body_size: float | None = None,
) -> StructureElement:
    title_size = label_size if body_size is None else body_size
    return StructureElement(
        source_role="LI",
        semantic_role="list_item",
        children=(
            StructureElement(
                "Lbl", "label", children=(_fragment(label, label_size, 1),)
            ),
            StructureElement(
                "LBody", "list_body", children=(_fragment(title, title_size, 2),)
            ),
        ),
    )


def _paragraph(text: str = "Body text", size: float = 7.0) -> StructureElement:
    return StructureElement(
        "P", "paragraph", children=(_fragment(text, size, 3),)
    )


def _document(*children: StructureElement) -> TaggedDocument:
    return TaggedDocument(Path("manual.pdf"), True, "en", (), children)


def _series(
    *labels: str,
    heading: float | None = 16.0,
    body: float = 7.0,
) -> TaggedDocument:
    children: list[StructureElement] = []
    for label in labels:
        children.extend((_chapter(label, f"Title {label}", heading), _paragraph(size=body)))
    return _document(StructureElement("L", "list", children=tuple(children)))


def _labels(document: TaggedDocument) -> tuple[str, ...]:
    return tuple(item.label for item in document.heading_promotions)


promote = promote_numbered_chapter_headings
```

Test that only direct `label` plus direct `list_body` children with exact ASCII labels `01` through `99` are candidates. Include positive labels `01`, `09`, `10` and negative labels `00`, `1.`, `(1)`, `①`, and a nested label.

The central positive assertion must be:

```python
promoted = promote_numbered_chapter_headings(
    _document(
        _chapter("01", "First", 16.0),
        _paragraph("Body", 7.0),
        _chapter("02", "Second", 16.0),
    )
)

assert [item.label for item in promoted.heading_promotions] == ["01", "02"]
assert [item.title for item in promoted.heading_promotions] == ["First", "Second"]
```

- [ ] **Step 2: Write sequence, typography, and series audit tests**

Add independent tests for:

```python
assert _labels(promote(_series("01", "02", "03"))) == ("01", "02", "03")
assert _labels(promote(_series("01", "03"))) == ()
assert _labels(promote(_series("01", "02", "02"))) == ()
assert _labels(promote(_series("02", "03"))) == ()
assert _labels(promote(_series("01"))) == ()
```

Add typography boundary tests:

```python
accepted = promote(_series("01", "02", heading=12.0, body=8.0))
assert accepted.heading_promotions[0].font_size_ratio == pytest.approx(1.5)
assert _labels(accepted) == ("01", "02")
assert _labels(promote(_series("01", "02", heading=11.9, body=8.0))) == ()

mismatched = _document(
    _chapter("01", "First", label_size=16.0, body_size=7.0),
    _paragraph(),
    _chapter("02", "Second", label_size=16.0, body_size=7.0),
)
assert _labels(promote(mismatched)) == ()
assert _labels(promote(_series("01", "02", heading=None, body=7.0))) == ()
```

Add two-series tests where every new `01` begins a series. Equal counts `(3, 3)` must pass cross-series consistency; `(3, 2)` must preserve locally valid promotions but add `numbered_heading_series_count_mismatch` and mark the audit inconsistent.

- [ ] **Step 3: Run the new test module and verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_numbered_heading_promotion.py -v
```

Expected: FAIL because the promotion model and module do not exist.

- [ ] **Step 4: Add immutable promotion audit models**

Append fields so existing `TaggedDocument` positional construction remains valid:

```python
@dataclass(frozen=True)
class HeadingPromotion:
    child_path: tuple[int, ...]
    level: int
    label: str
    title: str
    series_index: int
    heading_font_size: float
    body_font_size: float
    font_size_ratio: float
    promotion_reason: str


@dataclass(frozen=True)
class NumberedHeadingSeriesAudit:
    series_index: int
    labels: tuple[str, ...]
    valid_sequence: bool


@dataclass(frozen=True)
class TaggedDocument:
    source_path: Path
    marked: bool
    language: str | None
    role_map: tuple[tuple[str, str], ...]
    children: tuple[StructureElement | ContentFragment, ...]
    diagnostics: tuple[Diagnostic, ...] = ()
    heading_promotions: tuple[HeadingPromotion, ...] = ()
    numbered_heading_series: tuple[NumberedHeadingSeriesAudit, ...] = ()
    numbered_heading_series_consistent: bool | None = None
```

- [ ] **Step 5: Implement candidate extraction and weighted medians**

Create `numbered_heading_promotion.py` with these constants and public entry point:

```python
_LABEL = re.compile(r"^(?:0[1-9]|[1-9][0-9])$")
_MIN_SERIES_LENGTH = 2
_MIN_FONT_RATIO = 1.5
_MAX_LABEL_BODY_DIFFERENCE = 0.10
_PROMOTION_REASON = "numbered_chapter_structure_sequence_typography"


def promote_numbered_chapter_headings(document: TaggedDocument) -> TaggedDocument:
    visits = tuple(_walk(document.children))
    candidates = tuple(_candidate(visit) for visit in visits)
    candidates = tuple(item for item in candidates if item is not None)
    series = _split_at_01(candidates)
    promotions, audits, diagnostics = _evaluate_series(visits, series)
    counts = tuple(len(item.labels) for item in audits if item.valid_sequence)
    consistent = None if len(counts) < 2 else len(set(counts)) == 1
    if consistent is False:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="numbered_heading_series_count_mismatch",
                message="Numbered chapter series have different chapter counts",
                context={"series_counts": list(counts)},
            )
        )
    return replace(
        document,
        diagnostics=(*document.diagnostics, *diagnostics),
        heading_promotions=tuple(promotions),
        numbered_heading_series=tuple(audits),
        numbered_heading_series_consistent=consistent,
    )
```

Use a stable `child_path: tuple[int, ...]` produced by tree indexes, not semantic tag strings. Collect direct `label` and `list_body` children only. Recover visible text recursively with `join_text_parts`, normalize whitespace, and never translate or compare titles to a language dictionary.

Implement the character-weighted median over valid finite positive style sizes:

```python
def _weighted_median(samples: list[tuple[float, int]]) -> float | None:
    ordered = sorted((size, weight) for size, weight in samples if weight > 0)
    if not ordered:
        return None
    threshold = sum(weight for _, weight in ordered) / 2
    cumulative = 0
    for size, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return size
    raise AssertionError("non-empty weighted median did not return")
```

For a heading candidate use the smaller of the Label and List Body medians. Reject candidates when either median is missing, their relative difference exceeds 10%, or `heading_size / body_size < 1.5`.

- [ ] **Step 6: Implement profile-free series and body baseline boundaries**

Start a new series at every candidate whose label is `01`. A series spans from that candidate's traversal position to the next `01`; its body baseline contains styled fragments under `semantic_role == "paragraph"` in that span, excluding every candidate subtree. Use the same weighted median helper, with text length as weight.

Sequence validity is exact:

```python
expected = tuple(f"{number:02d}" for number in range(1, len(series) + 1))
actual = tuple(candidate.label for candidate in series)
valid_sequence = len(series) >= _MIN_SERIES_LENGTH and actual == expected
```

Emit explicit error diagnostics for invalid sequence, insufficient typography, and Label/List Body size mismatch. Include `series_index`, `child_path`, `page_index`, `label`, and available calculated sizes in each context.

- [ ] **Step 7: Run the pure domain tests**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_numbered_heading_promotion.py -v
```

Expected: PASS for format, structure, sequence, threshold, missing-data, equal-series, and mismatched-series cases.

- [ ] **Step 8: Commit the domain pass**

```powershell
git add src/tagged_pdf_extractor/domain/models.py src/tagged_pdf_extractor/domain/numbered_heading_promotion.py tests/test_numbered_heading_promotion.py
git commit -m "Detect numbered chapter headings from structure and typography"
```

### Task 4: Wire promotions into the use case and quality report

**Files:**
- Modify: `src/tagged_pdf_extractor/application/extract_document.py`
- Modify: `src/tagged_pdf_extractor/application/evaluate_quality.py`
- Modify: `tests/test_quality_evaluator.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing evaluator tests**

Build a `TaggedDocument` with two `HeadingPromotion` records and assert:

```python
report = QualityEvaluator().evaluate(document, baseline, xml_round_trip_ok=True)

assert report.metrics["heading_count"] == 2
assert report.metrics["numbered_heading_promotion_count"] == 2
assert report.metrics["numbered_heading_series"] == [
    {"series_index": 0, "labels": ["01", "02"], "valid_sequence": True}
]
assert report.hard_gates["numbered_heading_series_valid"] is True
assert report.hard_gates["numbered_heading_series_counts_consistent"] is True
assert report.hard_gates["has_heading"] is True
```

Add a mismatched-series test asserting the count-consistency gate is false and `status == "fail"`. Add an invalid-sequence diagnostic test asserting the series-valid gate is false.

- [ ] **Step 2: Run evaluator tests and verify new metrics are absent**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_quality_evaluator.py -v
```

Expected: FAIL on missing numbered-heading metrics and hard gates.

- [ ] **Step 3: Count promotion paths during quality traversal**

Build `promotion_by_path` once in `evaluate` and pass an index path through `_walk`. When a `StructureElement` path is promoted, count it as a heading, create a `heading_hierarchy` entry with `classification="numbered_chapter_promotion"`, `level=2`, exact Label/title, and all typography evidence. Continue traversing its children once so character and body metrics remain lossless.

Add metrics:

```python
"numbered_heading_promotion_count": len(document.heading_promotions),
"numbered_heading_series": [
    {
        "series_index": audit.series_index,
        "labels": list(audit.labels),
        "valid_sequence": audit.valid_sequence,
    }
    for audit in document.numbered_heading_series
],
```

Add hard gates:

```python
"numbered_heading_series_valid": all(
    audit.valid_sequence for audit in document.numbered_heading_series
),
"numbered_heading_series_counts_consistent": (
    document.numbered_heading_series_consistent is not False
),
```

Documents with no two-digit chapter candidates have an empty audit and pass both new gates; they still need a real or promoted heading to pass `has_heading`.

- [ ] **Step 4: Invoke the pure promotion pass after reading**

In `ExtractDocument.run`:

```python
document = self.reader.read(pdf_path)
document = promote_numbered_chapter_headings(document)
baseline = self.baseline_reader.read_text(pdf_path)
```

Add a CLI/use-case test with fake ports proving the document passed to `validate`, `evaluate`, and `write` is the promoted document and that the source reader result is not mutated.

- [ ] **Step 5: Run use-case, evaluator, and CLI tests**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_quality_evaluator.py tests/test_cli.py tests/test_output_bundle.py -v
```

Expected: PASS. Update exact hard-gate dictionaries in tests to include the two new keys instead of weakening equality assertions.

- [ ] **Step 6: Commit use-case and report integration**

```powershell
git add src/tagged_pdf_extractor/application/extract_document.py src/tagged_pdf_extractor/application/evaluate_quality.py tests/test_quality_evaluator.py tests/test_cli.py
git commit -m "Apply numbered heading promotion in extraction quality flow"
```

### Task 5: Render auditable semantic XML and Markdown headings

**Files:**
- Modify: `src/tagged_pdf_extractor/infrastructure/xml_writer.py`
- Modify: `src/tagged_pdf_extractor/infrastructure/markdown_writer.py`
- Modify: `tests/test_xml_writer.py`
- Modify: `tests/test_markdown_writer.py`

- [ ] **Step 1: Write a failing raw-versus-semantic XML test**

Create a document whose child path is promoted and assert:

```python
raw_item = raw_root.find(".//element[@semantic-role='list_item']")
semantic_heading = semantic_root.find(".//heading")

assert raw_item is not None
assert "promotion-reason" not in raw_item.attrib
assert semantic_heading is not None
assert semantic_heading.attrib == {
    "level": "2",
    "source-role": "LI",
    "promotion-reason": "numbered_chapter_structure_sequence_typography",
    "series-index": "0",
    "heading-font-size": "16",
    "body-font-size": "7",
    "font-size-ratio": "2.285714",
}
assert "".join(semantic_heading.itertext()) == "03Troubleshooting and Maintenance"
```

Use the XML writer's stable number formatting helper so integer-looking floats serialize without `.0` and ratios use at most six decimal places.

- [ ] **Step 2: Write a failing Markdown list-heading test**

Build semantic XML containing a heading directly under a list and assert:

```python
markdown = _render(
    tmp_path,
    """
    <list>
      <heading level="2"><label><text>03</text></label><list_body><text>Troubleshooting</text></list_body></heading>
      <list_item><label><text>1.</text></label><list_body><text>Normal step</text></list_body></list_item>
    </list>
    """,
)

assert "## 03 Troubleshooting" in markdown
assert "- 03 Troubleshooting" not in markdown
assert markdown.count("03 Troubleshooting") == 1
assert "1. Normal step" in markdown
```

- [ ] **Step 3: Run the focused writer tests and verify failure**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_xml_writer.py tests/test_markdown_writer.py -v
```

Expected: FAIL because promotion records are not yet consumed and semantic headings inside lists are flattened.

- [ ] **Step 4: Make semantic XML path-aware while leaving raw XML unchanged**

Build a `promotion_by_path` map in `write_semantic`, pass `child_path` through `_append_semantic_child`, and select the emitted tag with:

```python
promotion = promotion_by_path.get(child_path)
tag = "heading" if promotion is not None else (
    child.semantic_role
    if child.semantic_role in _SAFE_SEMANTIC_TAGS
    else "unknown"
)
```

When promoted, write the level and evidence attributes shown in Step 1. Preserve nested Label and List Body children, source text, MCIDs, and source order. Do not consult promotions in `write_raw`.

- [ ] **Step 5: Render actual semantic headings inside list containers**

In `_render_element`, before the generic atomic-tag branch, render actual headings:

```python
if element.tag == "heading":
    level = max(1, min(int(element.get("level", "1")), 6))
    text = cls._element_text(element)
    return [f"{'#' * level} {text}"] if text else []
```

Treat `heading` as a block in `_list_events`. Keep the existing `source_role_candidate` path behavior unchanged so old custom roles continue to render at their established shifted level.

- [ ] **Step 6: Run writer and bundle regression tests**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_xml_writer.py tests/test_markdown_writer.py tests/test_output_bundle.py -v
```

Expected: PASS, with no duplicate heading text and no change to raw source-role structure.

- [ ] **Step 7: Commit semantic and Markdown output support**

```powershell
git add src/tagged_pdf_extractor/infrastructure/xml_writer.py src/tagged_pdf_extractor/infrastructure/markdown_writer.py tests/test_xml_writer.py tests/test_markdown_writer.py
git commit -m "Render verified numbered chapters as semantic headings"
```

### Task 6: Verify ZC, ZA, and ZG source PDFs

**Files:**
- Modify: `tests/test_zc_integration.py`
- Modify: `tests/test_layout_regression.py`

- [ ] **Step 1: Update the ZC acceptance assertions**

Run extraction through `ExtractDocument`, not a manually separated reader/evaluator path, and assert:

```python
assert report.metrics["numbered_heading_promotion_count"] == 8
assert [audit["labels"] for audit in report.metrics["numbered_heading_series"]] == [
    ["01", "02", "03", "04"],
    ["01", "02", "03", "04"],
]
assert report.hard_gates["has_heading"] is True
assert report.hard_gates["numbered_heading_series_valid"] is True
assert report.hard_gates["numbered_heading_series_counts_consistent"] is True
```

Parse semantic XML and Markdown and assert all eight exact extracted titles appear once as `<heading level="2">` and `##` lines. Assert raw XML still contains them as source-role `LI` with direct `Lbl` and `LBody` children.

- [ ] **Step 2: Add ZA and ZG promotion assertions**

In `test_layout_regression.py`, retain all current structure and text-loss checks and add:

```python
def _series_labels(report: QualityReport) -> list[tuple[str, ...]]:
    return [
        tuple(item["labels"])
        for item in report.metrics["numbered_heading_series"]
    ]


assert za_report.metrics["numbered_heading_promotion_count"] == 3
assert _series_labels(za_report) == [("01", "02", "03")]
assert za_report.hard_gates["numbered_heading_series_counts_consistent"] is True

assert zg_report.metrics["numbered_heading_promotion_count"] == 25
assert _series_labels(zg_report) == [
    ("01", "02", "03", "04", "05"),
    ("01", "02", "03", "04", "05"),
    ("01", "02", "03", "04", "05"),
    ("01", "02", "03", "04", "05"),
    ("01", "02", "03", "04", "05"),
]
assert zg_report.hard_gates["numbered_heading_series_counts_consistent"] is True
```

Also assert ordinary `1.`, `2.` list items remain list items in semantic XML and do not become `##` headings.

- [ ] **Step 3: Run the required three-sample integration gate**

Run from the main repository root to resolve all PDFs, then enter the POC:

```powershell
$env:TAGGED_PDF_REQUIRE_SAMPLES = "1"
$env:TAGGED_PDF_ZC_SAMPLE = (Resolve-Path "samples\SUG_RAW\0_TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf").Path
$env:TAGGED_PDF_ZA_SAMPLE = (Resolve-Path "samples\SUG_RAW\0_TV_ZA\BN68-25099B-00_SUG_Y26 TV ALL_ZA_ENG_260126.0.pdf").Path
$env:TAGGED_PDF_ZG_SAMPLE = (Resolve-Path "samples\SUG_RAW\1_TV_ZG\BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf").Path
Set-Location ".worktrees\xml-markdown-review\samples\tagged_pdf_xml_poc"
.\.venv\Scripts\python -m pytest tests/test_zc_integration.py tests/test_layout_regression.py -v
```

Expected: PASS with ZC `8`, ZA `3`, and ZG `25` verified promotions, no unresolved MCIDs, and no forbidden XML controls.

- [ ] **Step 4: Inspect generated review artifacts**

Regenerate all three outputs into fresh temporary directories with `--overwrite`:

```powershell
.\.venv\Scripts\tagged-pdf-extract.exe "$env:TAGGED_PDF_ZC_SAMPLE" --output "tmp\heading_review_zc" --overwrite
.\.venv\Scripts\tagged-pdf-extract.exe "$env:TAGGED_PDF_ZA_SAMPLE" --output "tmp\heading_review_za" --overwrite
.\.venv\Scripts\tagged-pdf-extract.exe "$env:TAGGED_PDF_ZG_SAMPLE" --output "tmp\heading_review_zg" --overwrite
```

Expected: all three commands return exit code `0` with `status: pass`. Check the Markdown heading counts:

```powershell
Select-String -Path tmp\heading_review_zc\semantic_document.md -Pattern '^## 0[1-4] '
Select-String -Path tmp\heading_review_za\semantic_document.md -Pattern '^## 0[1-3] '
Select-String -Path tmp\heading_review_zg\semantic_document.md -Pattern '^## 0[1-5] '
```

Expected counts: ZC `8`, ZA `3`, ZG `25`. Open each `extraction_report.json` and confirm every promotion contains `heading_font_size`, `body_font_size`, `font_size_ratio`, `series_index`, exact source Label, and exact source title.

Use this audit command to verify the report evidence fields:

```powershell
.\.venv\Scripts\python.exe -c "import json; from pathlib import Path; roots=('heading_review_zc','heading_review_za','heading_review_zg'); required={'heading_font_size','body_font_size','font_size_ratio','series_index','label','title'}; [(lambda rows: print(root, len(rows), all(required <= set(row) for row in rows)))([row for row in json.loads((Path('tmp')/root/'extraction_report.json').read_text(encoding='utf-8'))['heading_hierarchy'] if row['classification']=='numbered_chapter_promotion']) for root in roots]"
```

Expected:

```text
heading_review_zc 8 True
heading_review_za 3 True
heading_review_zg 25 True
```

- [ ] **Step 5: Commit representative-PDF acceptance coverage**

```powershell
git add tests/test_zc_integration.py tests/test_layout_regression.py
git commit -m "Verify numbered chapter headings across ZC ZA and ZG"
```

### Task 7: Update reviewer documentation and run final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the human-review contract**

Document that:

- `## 01 ...` through `## NN ...` are verified numbered chapter promotions, not language-specific translations.
- The rule requires direct Label/List Body structure, contiguous `01` sequence, at least two candidates, Label/List Body size agreement within 10%, and a title/body ratio of at least 1.5.
- Each new `01` starts a profile-free series; multiple series must have equal counts.
- `raw_structure.xml` keeps the original list structure while `semantic_document.xml` carries promotion evidence.
- Font names are audit evidence only and are never hardcoded.
- Count mismatch or missing typography blocks an unattended quality pass and never fabricates a heading.

Replace the stale “all three samples fail only `has_heading`” statements with the verified Task 6 results: all three samples pass, with ZC `8`, ZA `3`, and ZG `25` numbered chapter promotions. If Task 6 produces any different result, stop and diagnose it instead of documenting a predicted success.

- [ ] **Step 2: Run the complete POC test suite**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests -v
```

Expected: PASS with no unexpected skips when the three required sample environment variables remain set.

- [ ] **Step 3: Run syntax compilation from the POC and repository roots**

Run in the POC:

```powershell
.\.venv\Scripts\python -m compileall src tests
```

Expected: exit code `0`.

Run the repository-required command from the main repository root:

```powershell
python -m compileall src tests scripts apps
```

Expected: exit code `0`.

- [ ] **Step 4: Review the final diff and working tree**

Run:

```powershell
git diff --check
git status --short
git diff --stat HEAD~5..HEAD
```

Expected: no whitespace errors; only the planned POC source, tests, and README are changed. `samples/tagged_pdf_xml_poc/tmp/` may remain untracked and must not be committed.

- [ ] **Step 5: Commit documentation**

```powershell
git add README.md
git commit -m "Document numbered chapter heading verification"
```

- [ ] **Step 6: Request code review before integration**

Use the `requesting-code-review` skill against the full implementation diff. Resolve any correctness findings, rerun the focused tests plus both compile commands, and keep generated PDF/XML/Markdown outputs untracked.
