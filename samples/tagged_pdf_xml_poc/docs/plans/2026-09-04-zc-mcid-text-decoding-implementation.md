# ZC MCID Text Decoding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the synthetic-content-stream flush workaround with deterministic MCID-aware text decoding so ZC C-FRA has zero forbidden controls while PDF structure, text order, and ENG output remain intact.

**Architecture:** Add a focused pypdf operation runner that reads the original `ContentStream.operations`, keeps pypdf's font and text state, and flushes accumulated text directly before marked-content boundaries without inserting fake `cm` operations. Keep `McidTextCollector` responsible for the MCID stack and diagnostics, then normalize list labels only at the Markdown presentation boundary. Preserve the existing `TaggedPdfReader`, domain models, XML formats, and output-bundle contract.

**Tech Stack:** Python 3.11+, pypdf 6.16.2, PyMuPDF baseline checks, XML ElementTree, pytest.

---

### Task 1: Lock the ZC C-FRA decoding defect with a failing integration test

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/tests/test_zc_integration.py`

- [ ] **Step 1: Replace the accepted-control assertion with the required clean-text contract**

In the existing ZC integration test, replace the assertion that accepts 608 controls with:

```python
assert report_data["metrics"]["forbidden_xml_control_count"] == 0
assert report_data["metrics"]["forbidden_xml_control_field_count"] == 0
assert "[CONTROL U+" not in markdown

normalized_markdown = re.sub(r"\s+", " ", markdown)
assert "Produit de catégorie II" in normalized_markdown
assert "Communiquez avec un centre de service homologué" in normalized_markdown
assert "Pour les modèles de 82 po, vous devrez être quatre" in normalized_markdown
assert "Le fait de tirer, de pousser ou de monter sur le téléviseur" in normalized_markdown
assert "Ne jamais placer un téléviseur dans une position instable" in normalized_markdown
assert "Wireless One Connect uniquement" in normalized_markdown
```

Keep the existing checks for 38 heading candidates, the exact OSD path, XML/Markdown text-token order, `unresolved_mcid_count == 0`, and output transaction behavior.

- [ ] **Step 2: Run the ZC test and verify RED**

```powershell
$env:TAGGED_PDF_ZC_SAMPLE = (Resolve-Path "..\SUG_RAW\0_TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf").Path
.venv\Scripts\python -m pytest tests\test_zc_integration.py -v
```

Expected: FAIL because `forbidden_xml_control_count` is 608 and one or more clean French phrases are corrupted.

- [ ] **Step 3: Commit the failing regression test**

```powershell
git add -- samples/tagged_pdf_xml_poc/tests/test_zc_integration.py
git commit -m "Test clean ZC C-FRA MCID decoding"
```

### Task 2: Add an operation runner that flushes text without rewriting the content stream

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_operation_text.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_pypdf_operation_text.py`
- Modify: `samples/tagged_pdf_xml_poc/pyproject.toml`

- [ ] **Step 1: Write focused failing tests for boundary flushes and original-operation preservation**

Build in-memory pages with the existing `PdfWriter`, `DecodedStreamObject`, and Helvetica fixture pattern. Test two adjacent MCIDs inside one text object:

```python
def test_runner_flushes_before_mcid_boundaries_without_synthetic_cm() -> None:
    page = _in_memory_page(
        b"BT /F1 12 Tf "
        b"/P << /MCID 2 >> BDC (First) Tj EMC "
        b"/P << /MCID 3 >> BDC (Deuxieme) Tj EMC ET"
    )
    original = list(page.get_contents().operations)
    active: list[int | None] = []
    captured: dict[int, list[str]] = {}

    def boundary(operator: bytes, operands: list[object]) -> None:
        if operator == b"BDC":
            active.append(int(operands[1]["/MCID"]))
        elif operator == b"EMC":
            active.pop()

    def text(value: str) -> None:
        if value and active and active[-1] is not None:
            captured.setdefault(active[-1], []).append(value)

    PypdfOperationTextRunner().run(page, on_boundary=boundary, on_text=text)

    assert {key: "".join(parts) for key, parts in captured.items()} == {
        2: "First",
        3: "Deuxieme",
    }
    assert page.get_contents().operations == original
    assert all(operator != b"cm" for _, operator in original)
```

Add tests proving that `TJ` arrays retain explicit word spacing, `Tf` font changes flush under the current MCID, `BT`/`ET` preserve text, and an active `Do` operation calls `on_xobject` without silently claiming support.

- [ ] **Step 2: Run the new unit tests and verify RED**

```powershell
.venv\Scripts\python -m pytest tests\test_pypdf_operation_text.py -v
```

Expected: collection fails because `pypdf_operation_text` does not exist.

- [ ] **Step 3: Raise the pypdf minimum to the inspected API baseline**

Change the dependency to:

```toml
dependencies = [
    "pypdf>=6.16.2,<7",
    "PyMuPDF>=1.26,<2",
]
```

This module deliberately uses `pypdf._font.Font` and `pypdf._text_extraction._text_extractor.TextExtraction`; the `<7` ceiling and compatibility tests make that private-API dependency explicit.

- [ ] **Step 4: Implement the runner over the untouched operations list**

Create these public classes and give `PypdfOperationTextRunner.run` the stated callable signature:

```python
from collections.abc import Callable
from typing import Any


class PypdfOperationTextError(RuntimeError):
    pass


class PypdfOperationTextRunner:
    """Run pypdf text state over original page operations."""
```

`run` receives `page: Any`, keyword-only `on_boundary: Callable[[bytes, list[Any]], None]`, `on_text: Callable[[str], None]`, and optional `on_xobject: Callable[[Any], None] | None`, and returns `None`.

Implement `run()` using these exact rules:

1. Resolve inherited `/Resources`, construct `font_resources`, and build each `Font` with `Font.from_font_resource()`.
2. Read `content = page.get_contents()` and iterate a snapshot `tuple(content.operations)` without assigning to `page` or `content.operations`.
3. Initialize `TextExtraction` with a visitor that forwards non-empty strings to `on_text`.
4. Before `BMC`, `BDC`, or `EMC`, call `extractor._flush_text()`, then call `on_boundary(operator, operands)`.
5. Process `'`, `"`, `TJ`, and `TD` with the same operator expansion used by pypdf 6.16.2 `_extract_text()`.
6. For `Do`, flush current text and call `on_xobject(operand)`; do not recurse into the Form XObject in this task.
7. Pass all other operators to `extractor.process_operation(operator, operands)`.
8. Call `extractor._flush_text()` once after the final operation.
9. Convert missing resources, malformed content streams, or unavailable pypdf helper attributes into `PypdfOperationTextError` with the original exception chained.

The `TJ` branch must use the current extractor space threshold and must not decode bytes separately:

```python
if operator == b"TJ":
    threshold = extractor._space_width * 0.95
    for item in operands[0] if operands else ():
        if isinstance(item, (str, bytes)):
            extractor.process_operation(b"Tj", [item])
        elif isinstance(item, (int, float)):
            if abs(float(item)) >= threshold and extractor.text and not extractor.text.endswith(" "):
                extractor.process_operation(b"Tj", [" "])
```

- [ ] **Step 5: Run focused tests and verify GREEN**

```powershell
.venv\Scripts\python -m pytest tests\test_pypdf_operation_text.py -v
```

Expected: all operation-runner tests pass.

- [ ] **Step 6: Commit the operation runner**

```powershell
git add -- samples/tagged_pdf_xml_poc/pyproject.toml samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_operation_text.py samples/tagged_pdf_xml_poc/tests/test_pypdf_operation_text.py
git commit -m "Add MCID-safe pypdf operation runner"
```

### Task 3: Replace the synthetic `cm` workaround in `McidTextCollector`

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/mcid_text.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_mcid_text.py`

- [ ] **Step 1: Update collector tests to inject the new runner**

Keep real in-memory PDF tests for normal operation. Replace fake pages that only implement `extract_text()` with a fake runner:

```python
class FakeRunner:
    def __init__(self, events: list[tuple[str, object]]) -> None:
        self.events = events

    def run(self, page, *, on_boundary, on_text, on_xobject=None) -> None:
        for kind, value in self.events:
            if kind == "boundary":
                operator, operands = value
                on_boundary(operator, operands)
            elif kind == "text":
                on_text(value)
            elif kind == "xobject" and on_xobject is not None:
                on_xobject(value)
```

Construct the collector as `McidTextCollector(runner=FakeRunner(events))`. Preserve existing expectations for nested MCIDs, inherited MCIDs, named properties, invalid MCIDs, unmatched `EMC`, unclosed scopes, empty tagged figures, and Form XObject diagnostics.

Add an assertion that the module no longer exposes or calls `_page_with_marked_content_flushes`.

- [ ] **Step 2: Run collector tests and verify RED**

```powershell
.venv\Scripts\python -m pytest tests\test_mcid_text.py -v
```

Expected: failures because `McidTextCollector` does not accept `runner` and still uses `page.extract_text()`.

- [ ] **Step 3: Wire the runner into the collector**

Use this constructor and callback split:

```python
class McidTextCollector:
    def __init__(self, runner: PypdfOperationTextRunner | None = None) -> None:
        self.runner = runner or PypdfOperationTextRunner()

    def collect(self, page: Any, page_index: int) -> McidTextResult:
        stack: list[int | None] = []
        parts: dict[int, list[str]] = {}
        seen_mcids: set[int] = set()
        diagnostics: list[Diagnostic] = []

        def on_text(value: str) -> None:
            if value and stack and stack[-1] is not None:
                parts.setdefault(stack[-1], []).append(value)

        self.runner.run(
            page,
            on_boundary=on_boundary,
            on_text=on_text,
            on_xobject=on_xobject,
        )
```

Move the existing BMC/BDC/EMC stack logic into `on_boundary` without changing MCID validation or named-property resolution. Move the existing `tagged_form_xobject_unsupported` diagnostic into `on_xobject`. Delete `_page_with_marked_content_flushes`, `_MARKED_CONTENT_BOUNDARIES`, `_IDENTITY_CM`, and the `copy` import.

Catch `PypdfOperationTextError` only to add page context and re-raise it; do not fall back to the corrupt synthetic-`cm` path.

- [ ] **Step 4: Run collector and reader tests and verify GREEN**

```powershell
.venv\Scripts\python -m pytest tests\test_mcid_text.py tests\test_pypdf_reader.py -v
```

Expected: all tests pass and no test observes inserted `cm` operations.

- [ ] **Step 5: Commit the collector replacement**

```powershell
git add -- samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/mcid_text.py samples/tagged_pdf_xml_poc/tests/test_mcid_text.py
git commit -m "Decode text at original MCID boundaries"
```

### Task 4: Make the ZC clean-text integration gate pass

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_operation_text.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/evaluate_quality.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_pypdf_operation_text.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_quality_evaluator.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_zc_integration.py`

- [ ] **Step 1: Run the ZC integration test against the new collector**

```powershell
$env:TAGGED_PDF_ZC_SAMPLE = (Resolve-Path "..\SUG_RAW\0_TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf").Path
.venv\Scripts\python -m pytest tests\test_zc_integration.py -v
```

Expected: the former 608-control assertion passes at zero and all six clean French phrase assertions pass. If this exact result does not occur, stop this task, record the failing phrase or metric, and return to root-cause analysis rather than adding a text replacement.

- [ ] **Step 2: Add page-level text quality metrics**

Extend the quality traversal with a page-indexed accumulator and publish it as `metrics["text_quality_by_page"]`. Assert the ZC result with:

```python
page_quality = report.metrics["text_quality_by_page"]
assert page_quality["0"] == {
    "fragment_count": 947,
    "character_count": 21978,
    "forbidden_xml_control_count": 0,
}
assert page_quality["1"]["fragment_count"] == 991
assert page_quality["1"]["character_count"] > 0
assert page_quality["1"]["forbidden_xml_control_count"] == 0
```

The ZC structure-fragment counts 947 and 991 are required; the clean C-FRA character count is computed by the evaluator because removing corrupted controls and glyphs legitimately changes the former total. Add a unit test with fragments on pages 0 and 1 that asserts independent fragment, character, and control counts. Do not infer language names in the generic evaluator.

In `test_zc_integration.py`, assert page `"0"` is the ENG page, page `"1"` is the C-FRA page, both have zero forbidden controls, and their structure-fragment counts remain 947 and 991.

- [ ] **Step 3: Verify the final ZC metrics and exact phrases**

Require all of these assertions:

```python
assert report.metrics["forbidden_xml_control_count"] == 0
assert report.metrics["forbidden_xml_control_field_count"] == 0
assert report.metrics["unresolved_mcid_count"] == 0
assert report.metrics["extraction_loss_diagnostic_total"] == 0
assert report.hard_gates["no_known_text_loss"] is True
```

Keep special-character checks as measured comparisons against the PyMuPDF baseline. Do not hard-code a pass until `/`, `:`, `[`, `]`, `(`, and `)` counts are equal or a specific PDF-source exception has evidence.

- [ ] **Step 4: Run all extraction-focused tests**

```powershell
.venv\Scripts\python -m pytest tests\test_pypdf_operation_text.py tests\test_mcid_text.py tests\test_pypdf_reader.py tests\test_quality_evaluator.py tests\test_xml_writer.py tests\test_zc_integration.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit the ZC decoding completion**

```powershell
git add -- samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_operation_text.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/evaluate_quality.py samples/tagged_pdf_xml_poc/tests/test_pypdf_operation_text.py samples/tagged_pdf_xml_poc/tests/test_quality_evaluator.py samples/tagged_pdf_xml_poc/tests/test_zc_integration.py
git commit -m "Fix ZC C-FRA composite font decoding"
```

### Task 5: Normalize unordered list labels in Markdown without changing XML evidence

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_zc_integration.py`

- [ ] **Step 1: Write failing list-label tests**

Add one unordered and one ordered fixture:

```python
def test_unordered_list_uses_structure_marker_without_extracted_glyph(tmp_path: Path) -> None:
    markdown = render("""
    <document><list><list_item>
      <label><text>Ł</text></label>
      <list_body><text>Power safety</text></list_body>
    </list_item></list></document>
    """, tmp_path)
    assert "- Power safety" in markdown
    assert "Ł" not in markdown


def test_numbered_list_preserves_meaningful_label(tmp_path: Path) -> None:
    markdown = render("""
    <document><list><list_item>
      <label><text>2.</text></label>
      <list_body><text>Attach the bracket</text></list_body>
    </list_item></list></document>
    """, tmp_path)
    assert "2. Attach the bracket" in markdown
```

- [ ] **Step 2: Run the two tests and verify RED**

```powershell
.venv\Scripts\python -m pytest tests\test_markdown_writer.py -k "unordered_list_uses_structure_marker or numbered_list_preserves" -v
```

Expected: the unordered result contains `- Ł Power safety` or the ordered label is rendered incorrectly.

- [ ] **Step 3: Classify labels by list semantics**

Add a helper that preserves only meaningful ordered labels:

```python
_ORDERED_LABEL = re.compile(
    r"^(?:\(?\d+[.)]?|[A-Za-z][.)]|[ivxlcdmIVXLCDM]+[.)])$"
)


@classmethod
def _list_marker(cls, label_text: str) -> str:
    normalized = cls._normalize_whitespace(label_text)
    return normalized if _ORDERED_LABEL.fullmatch(normalized) else "-"
```

Render the direct `<label>` text as the list marker only; do not append it again to `<list_body>`. This uses the label's structural role and avoids document-wide replacement of `Ł`, `Œ`, bullets, dashes, or other characters. Raw and Semantic XML remain unchanged.

- [ ] **Step 4: Verify ZC list output**

Add these integration assertions:

```python
assert "- Ł " not in markdown
assert "- Œ " not in markdown
assert "Ł" not in markdown
assert "Œ" not in markdown
```

Run:

```powershell
.venv\Scripts\python -m pytest tests\test_markdown_writer.py tests\test_zc_integration.py -v
```

Expected: all tests pass; nested items retain indentation and numbered instructions retain their labels.

- [ ] **Step 5: Commit Markdown list normalization**

```powershell
git add -- samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py samples/tagged_pdf_xml_poc/tests/test_zc_integration.py
git commit -m "Normalize extracted list labels in Markdown"
```

### Task 6: Run cross-layout regression, regenerate artifacts, and document the result

**Files:**
- Create: `samples/tagged_pdf_xml_poc/tests/test_layout_regression.py`
- Modify: `samples/tagged_pdf_xml_poc/README.md`

- [ ] **Step 1: Add optional ZA and ZG sample regression tests**

Use the same ancestor-search strategy as `_resolve_zc_pdf()` for these files:

```python
ZA_SAMPLE = Path("samples/SUG_RAW/0_TV_ZA/BN68-25099B-00_SUG_Y26 TV ALL_ZA_ENG_260126.0.pdf")
ZG_SAMPLE = Path("samples/SUG_RAW/1_TV_ZG/BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf")
```

For each available sample, run `TaggedPdfReader().read()` and assert:

```python
assert document.marked is True
assert report.metrics["unresolved_mcid_count"] == 0
assert report.metrics["forbidden_xml_control_count"] == 0
assert report.metrics["element_count"] > 0
assert report.metrics["body_count"] > 0
```

For ZG, keep `tagged_form_xobject_unsupported` as a separately reported known blocker; do not hide it or redefine `no_known_text_loss` as passing.

> Final-review correction (2026-09-04): direct resource inspection showed that all ten referenced ZG `/Im0` objects are `/Subtype /Image`, not `/Form`. The collector now resolves the actual subtype; these images are not text-loss blockers, while true Forms remain `tagged_form_xobject_unsupported`.

- [ ] **Step 2: Run the cross-layout tests**

```powershell
.venv\Scripts\python -m pytest tests\test_layout_regression.py -v
```

Expected: ZA and ZG pass the text/control/MCID assertions when sample files are available; otherwise each missing sample is explicitly skipped.

- [ ] **Step 3: Update the README with the new extraction contract**

Document these facts:

- MCID mapping is retained internally to connect structure nodes to page text.
- The collector processes the original operations list and no longer injects synthetic `cm` operations.
- `[CONTROL U+XXXX]` remains a visible diagnostic format but the accepted ZC result contains zero instances.
- Raw XML preserves source evidence; Markdown normalizes list markers for human review.
- The CLI may still exit 1 for unrelated heading-role or Form XObject hard gates even when all four artifacts are generated.

- [ ] **Step 4: Run full verification**

```powershell
.venv\Scripts\python -m pytest tests -q
.venv\Scripts\python -m compileall -q src tests
git diff --check
```

Expected: all tests pass except the documented Windows symlink skip; compileall and `git diff --check` exit 0.

- [ ] **Step 5: Regenerate the ZC review artifacts**

```powershell
.venv\Scripts\tagged-pdf-extract.exe "..\SUG_RAW\0_TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" --output "outputs\BN68-25100B-00" --overwrite
```

Inspect `semantic_document.md`, `semantic_document.xml`, and `extraction_report.json`. Confirm zero controls, all 38 heading candidates, exact OSD path preservation, clean French phrases, and normalized list markers. Record the CLI exit code and every remaining hard gate without treating artifact generation as a pass.

- [ ] **Step 6: Commit tests and documentation**

```powershell
git add -- samples/tagged_pdf_xml_poc/tests/test_layout_regression.py samples/tagged_pdf_xml_poc/README.md
git commit -m "Verify MCID decoding across tagged PDF layouts"
```

### Task 7: Final review and model-escalation check

**Files:**
- Review only: all files changed by Tasks 1-6

- [ ] **Step 1: Review the diff against the approved design**

Confirm no root `src/`, existing checklist metadata, Streamlit code, or unrelated user files changed. Confirm the extraction changes remain under `samples/tagged_pdf_xml_poc`.

- [ ] **Step 2: Apply the agreed stop condition**

Count failed implementation hypotheses recorded during Tasks 2-4. If three attempts against the same root cause failed, or if the solution requires implementing substantially more of the PDF text specification than the operation runner above, stop before another workaround and ask the user to switch from GPT-5.6 Sol medium to GPT-5.6 Sol high or approve a revised architecture.

- [ ] **Step 3: Record final evidence**

Report the test count, skipped tests, ZC control count, unresolved MCID count, heading candidate count, exact generated Markdown path, ZA/ZG regression result, CLI status, and remaining hard gates.
