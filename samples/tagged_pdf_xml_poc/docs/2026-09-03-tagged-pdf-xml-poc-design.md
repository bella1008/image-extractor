# Tagged PDF XML Extraction POC Design

## 1. Purpose

This project determines whether the logical structure embedded in a tagged PDF
can replace layout-specific text extraction as the foundation of a new manual
review system.

The first test document is:

`C:\Users\bella\image-extractor\samples\SUG_RAW\0_TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf`

The PDF catalog has already been confirmed to contain both `/Marked true` and a
`/StructTreeRoot` entry. The POC therefore treats the PDF structure tree as the
primary source of reading order and hierarchy.

## 2. Project Boundary

The project lives at `samples/tagged_pdf_xml_poc/` and is independent of the
existing application.

- It has its own `pyproject.toml`, package source, tests, CLI, and outputs.
- It must not import modules from the parent project's `src/` package.
- It may receive any PDF path through its CLI; the test PDF is not copied.
- It remains in the current Git repository during the POC.
- If the POC passes, the directory can be moved into a new repository without
  changing its internal imports or execution interface.

The POC does not modify the current extraction engine, checklist database,
comparison reports, or Streamlit application.

## 3. Scope

### Included

- Validate that the input is a tagged PDF.
- Traverse `/StructTreeRoot` in logical structure order.
- Resolve structure elements and marked-content references to source text.
- Preserve semantic roles such as document, part, section, heading, paragraph,
  list, list item, table, row, header cell, and data cell.
- Preserve Unicode and meaningful special characters used by OSD paths.
- Join PDF text fragments into readable lines and sentences without silently
  changing source characters.
- Produce raw and normalized XML outputs.
- Produce a machine-readable extraction quality report.
- Compare tagged-text coverage with an independent page-text baseline.
- Report unresolved references, unsupported tags, empty structural elements,
  duplicate content, and suspicious text gaps.

### Excluded from phase 1

- XML-to-Markdown conversion.
- OCR.
- Checklist evaluation, multilingual semantic comparison, or report UI.
- Buyer-specific and language-specific extraction rules.
- Modification of the source PDF.

## 4. Extraction Approaches Considered

### A. Structure-tree-first extraction - selected

Read the PDF logical structure tree and resolve its marked-content references.
This directly tests whether the source PDF's authored hierarchy is reliable.

### B. Structure and geometry hybrid extraction

Use coordinates to repair tag-tree output during extraction. This can improve
individual results but would hide whether tags alone are sufficient and could
reintroduce profile-specific rules too early.

### C. Geometry-only XML generation

Convert PyMuPDF blocks into XML. This is fast, but it does not validate the
tagged-PDF idea and is therefore unsuitable as the primary POC.

The selected design uses approach A for semantic output. Geometry/page-text
extraction is used only as an independent coverage measurement and never as a
silent repair path.

## 5. Architecture

The package uses small Clean Architecture boundaries without introducing
framework layers that the POC does not need.

```text
src/tagged_pdf_extractor/
  domain/
    models.py             Document tree, element, content fragment, diagnostics
  application/
    extract_document.py   Use case and extraction result
    evaluate_quality.py   Coverage and structural quality evaluation
  ports/
    pdf_reader.py         Abstract tagged-PDF reader contract
    output_writer.py      Abstract output contract
  infrastructure/
    pypdf_reader.py       PDF object/tree and marked-content implementation
    pymupdf_baseline.py   Independent page-text coverage baseline
    xml_writer.py         Raw and semantic XML serialization
    json_report_writer.py Quality report serialization
  cli.py                  Command-line composition root
```

Dependencies point inward. Domain and application modules do not import PDF or
XML libraries. Infrastructure implements the port contracts. The CLI is the
only composition root.

## 6. Data Flow

```text
PDF path
  -> tagged-PDF validation
  -> structure-tree traversal
  -> marked-content resolution
  -> immutable document tree
  -> conservative text joining
  -> semantic XML
  -> baseline text comparison
  -> quality report
```

Two XML files are produced:

- `raw_structure.xml`: source tag names, object references, MCIDs, page
  references, attributes, and unmodified resolved fragments for diagnostics.
- `semantic_document.xml`: normalized semantic element names and conservatively
  joined text for human inspection and downstream use.

The original fragments remain available in raw XML even when semantic XML
joins them. Normalization must therefore be auditable and reversible.

## 7. Text Preservation Rules

- Decode PDF text as Unicode without ASCII transliteration.
- Escape XML-reserved characters only at serialization time; parsing the XML
  must restore the original characters.
- Preserve characters such as `>`, `→`, `/`, `&`, `:`, brackets, parentheses,
  model codes, units, and punctuation.
- Do not normalize symbols into guessed equivalents.
- Remove line-break hyphenation only when an explicit conservative rule proves
  that the hyphen is a layout artifact. Otherwise preserve it.
- Join fragments according to logical tag order, whitespace evidence, and
  punctuation. Never use an LLM to reconstruct source text.
- Record every join decision that changes whitespace in the quality report.

## 8. Semantic Mapping

Known PDF standard structure types are mapped as follows:

| PDF tag | Semantic XML |
| --- | --- |
| `Document` | `document` |
| `Part`, `Art`, `Sect`, `Div` | same lower-case structural role |
| `H`, `H1`-`H6`, `Title` | `heading` with source role and level |
| `P` | `paragraph` |
| `L`, `LI`, `Lbl`, `LBody` | list hierarchy elements |
| `Table`, `TR`, `TH`, `TD` | table hierarchy elements |
| `Figure`, `Caption` | figure/caption elements |
| unknown role | `unknown` with the exact source role preserved |

PDF role-map aliases are resolved before semantic mapping. Unknown tags do not
cause content loss and are surfaced as warnings.

## 9. Error Handling

The CLI exits with a nonzero status for unreadable PDFs, missing structure
trees, malformed object references that prevent traversal, or output write
failure.

Recoverable defects such as an unsupported role, empty element, unresolved
single MCID, or coverage gap produce diagnostics and continue extraction. No
fallback content is inserted into semantic XML without being identified in the
report.

Outputs are written to a run-specific temporary directory and moved into the
requested output directory only after all required artifacts serialize
successfully. Existing outputs are not overwritten unless an explicit CLI
option allows it.

## 10. Outputs

For the initial document, the default output directory is:

`outputs/BN68-25100B-00/`

Required artifacts:

- `raw_structure.xml`
- `semantic_document.xml`
- `extraction_report.json`

The report contains PDF tag metadata, element counts, heading hierarchy,
special-character checks, tagged-text coverage, unresolved-reference counts,
unknown roles, whitespace join records, and the final gate status.

## 11. Quality Gates

The initial run passes only when all hard gates pass:

- The PDF is marked and has a structure tree.
- Structure traversal completes without a fatal cycle or broken root.
- At least one heading and one body-content element are recovered.
- No resolved source text is lost during XML serialization.
- XML files are well formed and round-trip parse successfully.
- Required OSD-path characters found in source fragments survive semantic XML
  serialization exactly.
- Every unresolved MCID or object reference is counted and identified.

The following are reported as measured findings rather than fixed pass
thresholds in the first run:

- Tagged-text coverage relative to page-text extraction.
- Empty structural element ratio.
- Unknown-role count.
- Suspicious sentence-fragment and whitespace-join counts.

After inspecting the first real output, numeric acceptance thresholds will be
defined from evidence rather than guessed in advance.

## 12. Testing Strategy

- Unit tests for structure-role mapping, role-map aliases, XML escaping,
  Unicode/special-character round trips, and conservative fragment joining.
- Adapter tests using small generated or hand-built PDF object fixtures for
  tree traversal, nested headings, lists, tables, unknown roles, and broken
  references.
- An integration test against the specified ZC PDF, skipped with an explicit
  reason when the external sample path is absent.
- Contract tests proving application code depends only on ports and the project
  does not import the parent `src` package.
- CLI tests for successful extraction, missing tags, invalid input, output
  collision, and report generation.

## 13. Decision After the POC

The project becomes the extraction foundation of a new manual-review system
only if human inspection confirms that headings, hierarchy, sentence
continuity, tables/lists, and OSD paths are materially more reliable than the
current layout-rule approach.

If tags are incomplete but useful, a later design may add an explicit repair
stage. That decision is outside this POC and must not be hidden inside the
initial extractor.
