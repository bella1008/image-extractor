# Semantic Markdown Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve complex table paragraph/list structure in review Markdown and render structurally detected, typography-backed subtitles without language-title hardcoding.

**Architecture:** Keep `semantic_document.xml` as the rendering source and retain the existing simple pipe-table path. Add a small domain detector that turns already-collected `TextStyle` evidence into immutable `SubtitleHint` records, serialize those hints as auditable paragraph attributes, and make the Markdown writer recursively render complex rows/cells. Icon recognition is a separate second implementation plan after these regenerated outputs pass human review.

**Tech Stack:** Python 3.11+, dataclasses, `xml.etree.ElementTree`, pypdf MCID text/style evidence, pytest, existing atomic output bundle.

---

## File Structure

- Create `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/subtitle_detection.py`: normalize PDF font weight, summarize paragraph evidence, and detect subtitle hints from table-cell structure.
- Create `samples/tagged_pdf_xml_poc/tests/test_subtitle_detection.py`: isolated positive and negative tests for language-independent subtitle detection.
- Modify `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`: add immutable `SubtitleHint` evidence and attach hints to `TaggedDocument`.
- Modify `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py`: run subtitle detection after numbered heading promotion.
- Modify `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`: serialize subtitle evidence onto the matching semantic paragraph without changing text or heading hierarchy.
- Modify `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`: recursively render complex table rows/cells and render a hinted paragraph as bold text.
- Modify `samples/tagged_pdf_xml_poc/tests/test_xml_writer.py`: verify exact subtitle evidence attributes and unchanged semantic text.
- Modify `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`: verify multi-paragraph cells, nested lists, multi-cell boundaries, empty cells, bold subtitles, and no regression in simple tables.
- Modify `samples/tagged_pdf_xml_poc/tests/test_layout_regression.py`: verify ZG structure, bold disposal subtitles, and unchanged ZA/ZG numbered headings.
- Modify `samples/tagged_pdf_xml_poc/tests/test_zc_integration.py`: verify ZC complex-table list separation and unchanged ZC numbered headings.

### Task 1: Recursive Complex-Table Markdown Rendering

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`

- [ ] **Step 1: Write failing tests for one-cell and multi-cell complex rows**

Add focused tests beside the existing unsafe-table fallback tests:

```python
def test_complex_single_cell_preserves_paragraphs_and_nested_lists(tmp_path: Path) -> None:
    markdown = _render(
        tmp_path,
        """
        <table><table_row><table_cell>
          <paragraph><text>Intro paragraph</text></paragraph>
          <list><list_item><text>Parent item</text>
            <list><list_item><text>Nested item</text></list_item></list>
          </list_item></list>
          <paragraph><text>Tail paragraph</text></paragraph>
        </table_cell></table_row></table>
        """,
    )

    assert "- 행 1:" in markdown
    assert "  Intro paragraph" in markdown
    assert "  - Parent item" in markdown
    assert "    - Nested item" in markdown
    assert "  Tail paragraph" in markdown
    assert "Intro paragraph Parent item Nested item Tail paragraph" not in markdown


def test_complex_multi_cell_keeps_cell_boundaries_and_empty_cells(tmp_path: Path) -> None:
    markdown = _render(
        tmp_path,
        """
        <table><table_row>
          <table_cell><paragraph><text>Left</text></paragraph></table_cell>
          <table_cell />
          <table_cell><list><list_item><text>Right item</text></list_item></list></table_cell>
        </table_row></table>
        """,
    )

    assert "  - 열 1:" in markdown
    assert "  - 열 2:" in markdown
    assert "    [빈 셀]" in markdown
    assert "  - 열 3:" in markdown
    assert markdown.index("Left") < markdown.index("[빈 셀]") < markdown.index("Right item")
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_markdown_writer.py -k "complex_single_cell or complex_multi_cell" -v
```

Expected: both tests fail because the current fallback flattens descendants into one row string and omits empty cells.

- [ ] **Step 3: Add block-preserving row/cell helpers**

Replace only the unsafe-table fallback in `_render_table`; retain the existing `safe_pipe_table` branch. Add helpers with these interfaces:

```python
@classmethod
def _render_complex_table(
    cls,
    table_children: list[ET.Element],
    promoted: dict[ET.Element, dict[str, object]],
) -> str:
    lines: list[str] = []
    row_index = 0
    for child in table_children:
        if child.tag != "table_row":
            cls._append_indented_blocks(
                lines, cls._render_element(child, promoted), indent="- "
            )
            continue
        row_index += 1
        lines.append(f"- 행 {row_index}:")
        cells = [
            value
            for value in cls._structural_children(child)
            if value.tag in _CELL_TAGS
        ]
        if len(cells) == 1:
            cls._append_table_cell(lines, cells[0], promoted, indent="  ")
            continue
        cell_index = 0
        for value in cls._structural_children(child):
            if value.tag in _CELL_TAGS:
                cell_index += 1
                lines.append(f"  - 열 {cell_index}:")
                cls._append_table_cell(lines, value, promoted, indent="    ")
            else:
                cls._append_indented_blocks(
                    lines, cls._render_element(value, promoted), indent="  "
                )
    return "\n".join(lines)


@classmethod
def _append_table_cell(
    cls,
    lines: list[str],
    cell: ET.Element,
    promoted: dict[ET.Element, dict[str, object]],
    *,
    indent: str,
) -> None:
    blocks = cls._render_children(cell, promoted)
    if not blocks:
        lines.append(f"{indent}[빈 셀]")
        return
    cls._append_indented_blocks(lines, blocks, indent=indent)


@staticmethod
def _append_indented_blocks(
    lines: list[str], blocks: list[str], *, indent: str
) -> None:
    for block_index, block in enumerate(blocks):
        if block_index and lines and lines[-1] != "":
            lines.append("")
        block_lines = block.splitlines() or [""]
        lines.extend(f"{indent}{line}" if line else "" for line in block_lines)
```

Change the final branch of `_render_table` to:

```python
return cls._render_complex_table(table_children, promoted)
```

Make `_render_table_with_promotions` delegate to the same structural row/cell rendering where possible so promoted headings remain in source order and do not reintroduce flattening.

- [ ] **Step 4: Run all Markdown writer tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_markdown_writer.py -v
```

Expected: all tests pass. Update existing fallback assertions only where the approved multiline structure intentionally replaces flattened output; keep every text-count and source-order assertion.

- [ ] **Step 5: Commit the complex-table renderer**

```powershell
git add -- samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py
git commit -m "Preserve complex table structure in Markdown"
```

### Task 2: Typography-Backed Subtitle Detection

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/subtitle_detection.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_subtitle_detection.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`

- [ ] **Step 1: Add the evidence model and failing detector tests**

Add to `domain/models.py`:

```python
@dataclass(frozen=True)
class SubtitleHint:
    child_path: tuple[int, ...]
    font_weight: int
    comparison_body_font_weight: int
    observed_line_count: int
    reason: str = "figure_table_title_stronger_than_following_body"
```

Add to `TaggedDocument`:

```python
subtitle_hints: tuple[SubtitleHint, ...] = ()
```

Create tests that build `StructureElement` and `ContentFragment` values directly:

```python
def _paragraph(text: str, font: str, *, mcid: int) -> StructureElement:
    return StructureElement(
        "P",
        "paragraph",
        children=(
            ContentFragment(
                page_index=0,
                mcid=mcid,
                text_parts=(text,),
                text_styles=(TextStyle(font, 6.5),),
            ),
        ),
    )


def test_detects_figure_table_title_stronger_than_following_body_without_words() -> None:
    figure_cell = StructureElement(
        "TD",
        "table_cell",
        children=(
            StructureElement(
                "P",
                "paragraph",
                children=(StructureElement("Figure", "figure"),),
            ),
        ),
    )
    text_cell = StructureElement(
        "TD",
        "table_cell",
        children=(
            _paragraph("Titre vérifié", "Subset+SamsungOne-600", mcid=1),
            _paragraph("(Texte explicatif)", "Subset+SamsungOne-600", mcid=2),
        ),
    )
    row = StructureElement("TR", "table_row", children=(figure_cell, text_cell))
    table = StructureElement("Table", "table", children=(row,))
    wrapper = StructureElement("P", "paragraph", children=(table,))
    body = _paragraph("Following body", "Subset+SamsungOne-400", mcid=3)
    section = StructureElement("Sect", "section", children=(wrapper, body))

    hints = detect_subtitle_hints((section,))

    assert hints == (
        SubtitleHint(
            child_path=(0, 0, 0, 0, 1, 0),
            font_weight=600,
            comparison_body_font_weight=400,
            observed_line_count=1,
        ),
    )


@pytest.mark.parametrize(
    "title_font,body_font,title_text",
    [
        ("SamsungOne-400", "SamsungOne-400", "Same weight"),
        ("UnknownFont", "SamsungOne-400", "Unresolved weight"),
        ("SamsungOne-600", "SamsungOne-400", "x" * 161),
    ],
)
def test_rejects_ambiguous_or_non_title_evidence(
    title_font: str, body_font: str, title_text: str
) -> None:
    section = _figure_title_section(
        title_text=title_text,
        title_font=title_font,
        qualifier_font=title_font,
        body_font=body_font,
    )
    assert detect_subtitle_hints((section,)) == ()
```

Define `_figure_title_section` in the test file using the exact structure from the positive example. Also cover: more than two observed non-empty title MCIDs, missing styles, mixed resolved/unresolved font names, missing figure-only sibling cell, visible text in the figure cell, missing following body sibling, a paragraph outside a table cell, and a non-leading paragraph.

- [ ] **Step 2: Run detector tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_subtitle_detection.py -v
```

Expected: import failure because `subtitle_detection.py` does not exist.

- [ ] **Step 3: Implement strict font normalization and traversal**

Create `domain/subtitle_detection.py` with public API:

```python
def normalize_font_weight(font_name: str | None) -> int | None:
    if not font_name:
        return None
    normalized = font_name.rsplit("+", 1)[-1].casefold()
    numeric = re.search(r"(?:^|[-_])(100|200|300|400|500|600|700|800|900)$", normalized)
    if numeric:
        return int(numeric.group(1))
    for token, weight in (
        ("black", 900),
        ("extrabold", 800),
        ("semibold", 600),
        ("demibold", 600),
        ("medium", 500),
        ("regular", 400),
        ("normal", 400),
        ("light", 300),
    ):
        if token in normalized.replace("-", "").replace("_", ""):
            return weight
    return None


def detect_subtitle_hints(
    children: tuple[StructureElement | ContentFragment, ...],
) -> tuple[SubtitleHint, ...]:
    hints: list[SubtitleHint] = []

    def visit(
        values: tuple[StructureElement | ContentFragment, ...],
        path: tuple[int, ...],
    ) -> None:
        for index, value in enumerate(values):
            child_path = (*path, index)
            if not isinstance(value, StructureElement):
                continue
            hint = _subtitle_hint_from_sibling_pair(values, index, path)
            if hint is not None:
                hints.append(hint)
            visit(value.children, child_path)

    visit(children, ())
    return tuple(hints)
```

Implement `_subtitle_hint_from_sibling_pair` so the current structural child is a wrapper containing one table, the next direct sibling is a body paragraph, and the table has a row with a figure-only cell immediately followed by a text cell. The text cell's first two direct structural children must be paragraphs. The leading title must contain 1–160 normalized characters and at most two distinct non-empty `(page_index, mcid)` line keys. Compare its weighted-median font weight with the following body sibling, not with the same-cell qualifier; require a difference of at least 100. Every non-empty title and body text part must have a style with a resolvable font name, and every contributing fragment must have `page_index >= 0` and a non-`None` MCID. Weight samples use visible-character count, not fragment count. Return at most one hint for each qualifying table row and deduplicate by exact title child path.

- [ ] **Step 4: Run subtitle unit tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_subtitle_detection.py tests/test_numbered_heading_promotion.py -v
```

Expected: all tests pass; numbered heading promotion remains unchanged.

- [ ] **Step 5: Commit domain subtitle evidence**

```powershell
git add -- samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/subtitle_detection.py samples/tagged_pdf_xml_poc/tests/test_subtitle_detection.py
git commit -m "Detect table subtitles from typography evidence"
```

### Task 3: Serialize and Render Subtitle Hints

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_xml_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_output_bundle.py`

- [ ] **Step 1: Write failing XML and Markdown tests**

Add an XML writer test asserting the exact attributes on the hinted paragraph:

```python
assert subtitle.attrib == {
    "display-role": "subtitle",
    "subtitle-reason": "figure_table_title_stronger_than_following_body",
    "font-weight": "600",
    "comparison-body-font-weight": "400",
    "observed-line-count": "2",
}
assert "".join(subtitle.itertext()) == "Generic title"
```

Add a Markdown writer test using semantic XML attributes, not literal title matching:

```python
def test_renders_subtitle_hint_as_bold_without_heading_promotion(tmp_path: Path) -> None:
    markdown = _render(
        tmp_path,
        """
        <table><table_row><table_cell>
          <paragraph display-role="subtitle" subtitle-reason="figure_table_title_stronger_than_following_body"
                     font-weight="600" comparison-body-font-weight="400" observed-line-count="1">
            <text>Arbitrary localized title</text>
          </paragraph>
          <paragraph><text>(Qualifier)</text></paragraph>
        </table_cell></table_row></table>
        """,
    )
    assert "**Arbitrary localized title**" in markdown
    assert "## Arbitrary localized title" not in markdown
    assert markdown.index("**Arbitrary localized title**") < markdown.index("(Qualifier)")
```

Add an output-bundle test that verifies subtitle attributes survive validation and do not enter `heading_hierarchy`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_xml_writer.py tests/test_markdown_writer.py tests/test_output_bundle.py -k "subtitle" -v
```

Expected: failures because hints are not attached, serialized, or rendered.

- [ ] **Step 3: Wire detection into extraction**

In `ExtractDocument.run`, keep numbered heading promotion first and then attach subtitle hints:

```python
document = self.reader.read(pdf_path)
document = promote_numbered_chapter_headings(document)
document = detect_table_subtitles(document)
```

Expose this wrapper from `subtitle_detection.py`:

```python
def detect_table_subtitles(document: TaggedDocument) -> TaggedDocument:
    return replace(
        document,
        subtitle_hints=detect_subtitle_hints(document.children),
    )
```

- [ ] **Step 4: Serialize evidence by exact child path**

In `XmlDocumentWriter.write_semantic`, build `subtitle_by_path` and reject duplicate paths:

```python
subtitle_by_path = {hint.child_path: hint for hint in document.subtitle_hints}
if len(subtitle_by_path) != len(document.subtitle_hints):
    raise ValueError("duplicate subtitle hint path")
```

Pass the mapping through `_append_semantic_child`. When the current `child_path` matches and the semantic tag is `paragraph`, append the five approved attributes. After traversal, assert every hint path was consumed. Reject a hint targeting a heading or non-paragraph rather than silently applying it.

- [ ] **Step 5: Render hinted paragraphs as bold Markdown blocks**

Before ordinary paragraph rendering in `_render_element`, add:

```python
if element.tag == "paragraph" and element.get("display-role") == "subtitle":
    text = cls._element_text(element)
    return [f"**{cls._escape_emphasis_text(text)}**"] if text else []
```

Add an emphasis helper that escapes only syntax that could break the bold wrapper:

```python
@staticmethod
def _escape_emphasis_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("*", r"\*").replace("_", r"\_")
```

Do not convert subtitle hints into heading candidates and do not modify numbered heading rendering.

- [ ] **Step 6: Run focused and compatibility tests**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_xml_writer.py tests/test_markdown_writer.py tests/test_output_bundle.py tests/test_numbered_heading_promotion.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit the subtitle pipeline**

```powershell
git add -- samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py samples/tagged_pdf_xml_poc/tests/test_xml_writer.py samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py samples/tagged_pdf_xml_poc/tests/test_output_bundle.py
git commit -m "Render typography-backed subtitles in Markdown"
```

### Task 4: ZC, ZA, and ZG Sample Regression Gates

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/tests/test_layout_regression.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_zc_integration.py`

- [ ] **Step 1: Add failing structure assertions to sample tests**

Add helpers that assert structure rather than line numbers:

```python
def _assert_separate_markdown_lines(markdown: str, values: tuple[str, ...]) -> None:
    lines = [line.strip() for line in markdown.splitlines()]
    for value in values:
        assert any(line.endswith(value) for line in lines), value
    positions = [markdown.index(value) for value in values]
    assert positions == sorted(positions)
```

For ZG, assert both verified titles are bold and their qualifiers are later separate lines:

```python
markdown = artifacts.semantic_markdown.read_text(encoding="utf-8")
assert "**Correct Disposal of This Product (Waste Electrical & Electronic Equipment)**" in markdown
assert "**Correct disposal of batteries in this product**" in markdown
assert markdown.count("(Applicable in countries with separate collection systems)") == 2
assert "## Correct Disposal" not in markdown
```

Locate the ZG `CLASS 1 LASER PRODUCT` and EMC/Safety/Radio source blocks by semantic text, then assert their list items/cells appear on separate Markdown lines and in source order. For ZC, locate the package-content and title-plus-three-item list blocks and assert every semantic list item has its own Markdown bullet line. Keep the existing `_assert_numbered_headings` calls unchanged.

- [ ] **Step 2: Run required sample tests and verify RED or targeted skips**

From the repository root, set required sample paths and run:

```powershell
$env:TAGGED_PDF_REQUIRE_SAMPLES = "1"
$env:TAGGED_PDF_ZC_SAMPLE = (Resolve-Path "samples\SUG_RAW\0_TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf").Path
$env:TAGGED_PDF_ZA_SAMPLE = (Resolve-Path "samples\SUG_RAW\0_TV_ZA\BN68-25099B-00_SUG_Y26 TV ALL_ZA_ENG_260126.0.pdf").Path
$env:TAGGED_PDF_ZG_SAMPLE = (Resolve-Path "samples\SUG_RAW\1_TV_ZG\BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf").Path
Set-Location samples\tagged_pdf_xml_poc
.\.venv\Scripts\python -m pytest tests/test_zc_integration.py tests/test_layout_regression.py -v
```

Expected before final adjustments: the new exact structural assertions expose any remaining flattening or missed subtitle evidence; existing heading assertions continue to pass.

- [ ] **Step 3: Make minimal generic fixes revealed by real samples**

Adjust only the generic complex-table renderer or typography detector. Do not add literal `Correct Disposal` checks, buyer-title dictionaries, language translations, or changes to `numbered_heading_promotion.py`. Every discovered edge case receives a focused unit regression test before its implementation change.

- [ ] **Step 4: Re-run sample regressions and verify GREEN**

Run the command from Step 2 again.

Expected: ZC, ZA, and ZG extraction tests pass; all existing numbered chapter heading counts/text remain unchanged; new structural assertions pass.

- [ ] **Step 5: Commit sample gates**

```powershell
git add -- samples/tagged_pdf_xml_poc/tests/test_zc_integration.py samples/tagged_pdf_xml_poc/tests/test_layout_regression.py
git commit -m "Gate structured Markdown across ZC ZA and ZG"
```

### Task 5: Full Verification and Review Output Regeneration

**Files:**
- Verify only: `samples/tagged_pdf_xml_poc/src/`
- Verify only: `samples/tagged_pdf_xml_poc/tests/`
- Generate ignored review artifacts under `samples/tagged_pdf_xml_poc/outputs/`

- [ ] **Step 1: Run the full POC test suite**

Run inside `samples/tagged_pdf_xml_poc` with the three required sample environment variables from Task 4:

```powershell
.\.venv\Scripts\python -m pytest tests -v
```

Expected: all tests pass, with only intentionally documented skips unrelated to available required samples.

- [ ] **Step 2: Run POC and repository compile checks**

Run inside the POC:

```powershell
.\.venv\Scripts\python -m compileall src tests
```

Run from the repository worktree root:

```powershell
python -m compileall src tests scripts apps
```

Expected: both commands exit `0` without syntax errors.

- [ ] **Step 3: Regenerate three fresh review bundles**

Run from `samples/tagged_pdf_xml_poc`:

```powershell
.\.venv\Scripts\tagged-pdf-extract.exe "$env:TAGGED_PDF_ZC_SAMPLE" --output "outputs\structured_markdown_zc_260905" --overwrite
.\.venv\Scripts\tagged-pdf-extract.exe "$env:TAGGED_PDF_ZA_SAMPLE" --output "outputs\structured_markdown_za_260905" --overwrite
.\.venv\Scripts\tagged-pdf-extract.exe "$env:TAGGED_PDF_ZG_SAMPLE" --output "outputs\structured_markdown_zg_260905" --overwrite
```

Expected: each command exits `0` and writes `semantic_document.md`, `semantic_document.xml`, `raw_structure.xml`, and `extraction_report.json` atomically.

- [ ] **Step 4: Run a no-hardcoding and regression audit**

Run:

```powershell
rg -n "Correct Disposal|disposal of batteries" src
rg -n "numbered_chapter_structure_sequence_typography" outputs/structured_markdown_zc_260905/extraction_report.json outputs/structured_markdown_za_260905/extraction_report.json outputs/structured_markdown_zg_260905/extraction_report.json
```

Expected: the first command finds no runtime source matches. The second finds the existing numbered-heading evidence in all three reports.

- [ ] **Step 5: Confirm generated artifacts remain untracked**

Confirm `git status --short` shows no generated output files and still shows the pre-existing untracked `samples/tagged_pdf_xml_poc/tmp/` directory untouched:

```powershell
git status --short
```

Expected: no tracked source/test changes remain after the earlier task commits. Do not add `outputs/` or `tmp/` to Git.

## Follow-on Plan Boundary

After the user reviews the regenerated Markdown, write a separate implementation plan for the verified icon catalog and conservative icon resolver. Tesseract/manual-code OCR and detailed `Declaration of Conformity` hierarchy remain deferred in `TODO.md` and are not part of this plan.
