# Semantic XML to Markdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a single human-readable `semantic_document.md` beside the existing XML and JSON artifacts while preserving document order, heading candidates, lists, tables, OSD paths, and visible extraction defects.

**Architecture:** Add a focused Markdown renderer that reads the already-serialized Semantic XML plus `QualityReport.heading_hierarchy`. The output bundle writes the Markdown file into the same staging directory and publishes all four artifacts through a lock-protected, crash-aware transaction with rollback for caught failures. Existing-directory publication replaces files sequentially, so cooperating readers must not read while the sibling `.<output>.lock` exists; hard termination can require manual review.

**Tech Stack:** Python 3.11+, standard-library `xml.etree.ElementTree`, dataclasses, pytest.

---

### Task 1: Render semantic XML structures as Markdown

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`

- [ ] **Step 1: Write failing tests for headings, paragraphs, lists, tables, figures, controls, and OSD text**

Create fixtures with the same path convention as the report, for example `/document[0]/article[0]/section[0]/paragraph[0]`, and assert:

```python
def test_writer_promotes_report_candidates_and_preserves_document_order(tmp_path):
    semantic = tmp_path / "semantic_document.xml"
    semantic.write_text(
        """<?xml version='1.0' encoding='utf-8'?>
<document><document><article><section>
  <paragraph><text> Warning! Important </text><text>Safety Instructions</text></paragraph>
  <paragraph><text>( &gt; Settings &gt; Support / Tips: [Open])</text></paragraph>
</section></article></document></document>""",
        encoding="utf-8",
    )
    report = QualityReport(
        "fail", {}, {}, (),
        heading_hierarchy=({
            "structure_path": "/document[0]/article[0]/section[0]/paragraph[0]",
            "source_role": "NoTOC-Heading1",
            "semantic_role": "paragraph",
            "level": 1,
            "joined_text": " Warning! Important Safety Instructions",
            "title": None,
            "classification": "source_role_candidate",
        },),
    )
    output = tmp_path / "semantic_document.md"

    MarkdownDocumentWriter().write(semantic, report, output, source_name="manual.pdf")

    text = output.read_text(encoding="utf-8")
    assert "## Warning! Important Safety Instructions" in text
    assert "( > Settings > Support / Tips: [Open])" in text
    assert text.index("## Warning!") < text.index("( > Settings")
```

Add separate tests proving list items use `-`, rectangular tables use Markdown pipe rows, irregular tables fall back to row lists, an empty figure becomes `[그림: 텍스트 없음]`, and `<control code="0003"/>` becomes `[CONTROL U+0003]`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
.venv\Scripts\python -m pytest tests\test_markdown_writer.py -v
```

Expected: collection fails because `tagged_pdf_extractor.infrastructure.markdown_writer` does not exist.

- [ ] **Step 3: Implement the minimal renderer**

Implement `MarkdownDocumentWriter.write(semantic_xml, report, output, *, source_name)` and focused private helpers for heading lookup, structural-child traversal, control-aware text decoding, recursive element rendering, table rendering, and atomic UTF-8 writing. Structural-child traversal must exclude only the synthetic `<attributes>` container; `<text>` children still count when reconstructing the report's child-index paths.

Only `classification == "source_role_candidate"` and report entries whose path resolves are promoted. Reject duplicate candidate paths and candidates whose paths overlap through an ancestor/descendant relationship. Render PDF heading level 1 as Markdown `##`, clamping deeper levels to Markdown `######`; the two `Cover_Title` candidates whose level is `None` use PDF level 1. Normalize whitespace between adjacent `<text>` fragments without changing punctuation. Decode control nodes with `decode_data_element`, replacing XML-illegal characters with `[CONTROL U+XXXX]`. Escape table-cell pipes, Markdown-significant line prefixes, and source link-reference/footnote definition lines; do not alter ordinary inline `>`, `/`, `:`, brackets, parentheses, ampersands, URLs, or reference uses.

Write UTF-8 with `\n` line endings through a temporary sibling file and `os.replace`. Reparse the Semantic XML before publication and raise `ValueError` for a candidate path that cannot be resolved; this keeps heading-count validation strict instead of silently downgrading a heading.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the same pytest command. Expected: all tests in `test_markdown_writer.py` pass.

- [ ] **Step 5: Commit Task 1 files only**

```powershell
git add -- samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py
git commit -m "Add semantic XML Markdown renderer"
```

### Task 2: Publish Markdown as a fourth transaction artifact

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/output_bundle.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_output_bundle.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_cli.py`

- [ ] **Step 1: Write failing artifact and transaction tests**

Extend test helpers to construct:

```python
ExtractionArtifacts(
    raw_xml=root / "raw_structure.xml",
    semantic_xml=root / "semantic_document.xml",
    report_json=root / "extraction_report.json",
    semantic_markdown=root / "semantic_document.md",
)
```

Assert `REQUIRED_OUTPUT_NAMES` contains all four names; a successful write creates valid Markdown; collisions on `semantic_document.md` are rejected unless `overwrite=True`; and a forced failure while publishing the fourth file restores all old artifacts.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
.venv\Scripts\python -m pytest tests\test_output_bundle.py tests\test_cli.py -v
```

Expected: failures because `ExtractionArtifacts.semantic_markdown` and the fourth required output are absent.

- [ ] **Step 3: Add Markdown to the artifact transaction**

Add `semantic_markdown: Path` to `ExtractionArtifacts`. Define:

```python
MARKDOWN_NAME = "semantic_document.md"
REQUIRED_OUTPUT_NAMES = (
    RAW_XML_NAME,
    SEMANTIC_XML_NAME,
    REPORT_JSON_NAME,
    MARKDOWN_NAME,
)
```

Construct the fourth artifact path wherever `ExtractionArtifacts` is created. In `_write_and_validate_staging`, first write and parse both XML files, then write the report JSON, then call:

```python
self.markdown_writer.write(
    staging / SEMANTIC_XML_NAME,
    report,
    staging / MARKDOWN_NAME,
    source_name=document.source_path.name,
)
```

Validate the Markdown as non-empty UTF-8 and confirm every accepted heading candidate occurs exactly once with its expected Markdown prefix. Keep all fingerprint, collision, backup, rollback, and publication loops driven by `REQUIRED_OUTPUT_NAMES`, so the existing lock and rollback protections apply to the fourth file. Do not claim atomic multi-file visibility for publication into an existing directory.

- [ ] **Step 4: Run focused transaction tests and verify GREEN**

Run the same pytest command. Expected: all output-bundle and CLI tests pass.

- [ ] **Step 5: Commit Task 2 files only**

```powershell
git add -- samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/output_bundle.py samples/tagged_pdf_xml_poc/tests/test_output_bundle.py samples/tagged_pdf_xml_poc/tests/test_cli.py
git commit -m "Publish Markdown with extraction artifacts"
```

### Task 3: Prove behavior against the ZC tagged PDF

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/tests/test_zc_integration.py`
- Modify: `samples/tagged_pdf_xml_poc/README.md`

- [ ] **Step 1: Add a failing integration assertion**

After the existing ZC extraction, assert:

```python
markdown = artifacts.semantic_markdown.read_text(encoding="utf-8")
import re
assert len(re.findall(r"(?m)^#{2,6} ", markdown)) == 38
assert "## Before Reading This Simple User Guide" in markdown
assert "Troubleshooting" in markdown
assert "Specifications" in markdown
assert "Dépannage" in markdown
assert "Spécifications" in markdown
assert "( > left directional button > Settings > Support > Tips and User Guides > Open User Guide)" in markdown
assert markdown.count("[CONTROL U+") == report.metrics["forbidden_xml_control_count"]
```

Also compare the ordered, normalized visible text tokens from Semantic XML with their positions in Markdown, allowing only heading prefixes, list markers, table delimiters, figure placeholders, and control-code notation.

- [ ] **Step 2: Run the integration test and verify RED**

```powershell
$env:TAGGED_PDF_ZC_SAMPLE = (Resolve-Path "..\SUG_RAW\0_TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf").Path
.venv\Scripts\python -m pytest tests\test_zc_integration.py -v
```

Expected: failure if heading paths, level-less `Cover_Title` candidates, controls, tables, or ordered text are not handled by the renderer.

- [ ] **Step 3: Fix only demonstrated renderer edge cases and document the output**

Update `README.md` to list `semantic_document.md` as the first file a non-developer should open. Explain that Markdown headings are source-role candidates, not verified standard PDF headings; controls are visible extraction defects; and Raw XML plus JSON remain the audit sources. Do not add translation, OCR, or text correction.

- [ ] **Step 4: Run focused and full verification**

```powershell
.venv\Scripts\python -m pytest tests\test_markdown_writer.py tests\test_output_bundle.py tests\test_cli.py tests\test_zc_integration.py -v
.venv\Scripts\python -m pytest tests -v
.venv\Scripts\python -m compileall src tests
```

Expected: all tests pass except the already documented Windows symlink skip; compileall exits 0.

- [ ] **Step 5: Generate and inspect the requested file**

```powershell
.venv\Scripts\tagged-pdf-extract.exe "..\SUG_RAW\0_TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" --output "outputs\BN68-25100B-00" --overwrite
```

Expected: exit code 1 because the existing extraction quality gates still report the known heading/special-character failures, but `outputs/BN68-25100B-00/semantic_document.md` is committed together with the other three artifacts and contains the known OSD path plus all 38 review headings.

- [ ] **Step 6: Commit Task 3 files only**

```powershell
git add -- samples/tagged_pdf_xml_poc/tests/test_zc_integration.py samples/tagged_pdf_xml_poc/README.md
git commit -m "Verify Markdown output for ZC tagged PDF"
```

### Task 4: Final review

**Files:**
- Review only: all files changed by Tasks 1–3

- [ ] **Step 1: Inspect the generated Markdown manually**

Check the beginning, English/French boundary, safety tables, OSD path, `Troubleshooting`/`Specifications`, `Dépannage`/`Spécifications`, control markers, and final copyright/contact sections.

- [ ] **Step 2: Confirm scope and clean working changes**

Use `git diff` restricted to the POC files and confirm no parent-project extraction logic or unrelated user files changed.

- [ ] **Step 3: Record final verification evidence**

Report the test counts, expected CLI exit code, generated Markdown path, heading count, control-marker count, and any remaining source-PDF extraction defects without describing them as Markdown conversion failures.
