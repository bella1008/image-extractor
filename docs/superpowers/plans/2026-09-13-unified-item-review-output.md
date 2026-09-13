# Unified Item Review Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store the checked item observation and its user workbook in one run directory, stop producing HTML for new runs, and simplify the workbook to user-relevant fields.

**Architecture:** The observation service remains the owner of `item_observation.json` and its completion receipt. The Excel exporter appends exclusively created Excel artifacts to that already completed run directory and publishes a separate Excel receipt last. The UI accepts one run directory, always validates the observation, and automatically offers the workbook only when its same-directory receipt is complete. Legacy JSON+HTML observation receipts remain readable but no new HTML is created or exposed.

**Tech Stack:** Python 3.12, pytest, Streamlit AppTest, read-only openpyxl validation, bundled Node.js and `@oai/artifact-tool` for XLSX authoring.

---

## File map

### Execution record — 2026-09-13

Tasks 1–4 implementation and verification are complete. The unchecked boxes below preserve the original proposed command sequence, not the current status. Actual execution used these documented adjustments:

- Added `tests/test_unified_item_output.py` first: 15 failures and 1 pass established the new-contract RED baseline. Updated focused suites then passed (114 passed, 2 optional backend skips before enabling the backend).
- Final full suite with the real authoring backend enabled: **503 passed in 104.32s**, including both real XLSX integration cases. Compileall, pip check and Git whitespace validation passed.
- New observation receipts explicitly use schema v2 with JSON only; archived v1 receipts require JSON plus HTML. Excel view is v2. Schema-specific artifact sets prevent accidental weakening of archived integrity checks.
- Same-directory export additionally uses an exclusive writer lock and refuses pre-existing complete/partial artifacts without invalidating an earlier successful export. UI checks partial and active export state.
- Generated `outputs/item_review_zc_20260913_unified/` from the PDF afresh rather than reusing the older extraction bundle. New HTML is absent. Saved workbook has Summary 12 rows, 14 items and 26 evidence rows. All retained cell values match the earlier r2 workbook, whose hash is unchanged.
- Rendered five readable ranges across the three sheets, splitting wide detail sheets instead of producing three overly wide previews. All five were visually inspected. Real-result AppTest confirmed one folder input, 14 rows and JSON/Excel downloads only.
- Independent read-only code review found no actionable correctness, regression or data-loss issue. Original checklist data, extraction code and other worktrees were not edited.
- Instead of the four intermediate commits below, keep the coupled service/exporter/UI contracts, tests and documentation in one scoped implementation checkpoint after verification. Pre-change checkpoint: `fc3e74f`; resolve the implementation checkpoint with `git log -1 --format=%H -- src/item_review_excel.py`.

Browser visual acceptance, full report integration and complete PC deployment remain outside this plan.

- `src/item_review_service.py`: publish JSON-only new observation runs and read both new and legacy receipts.
- `src/item_review_excel.py`: build the simplified three-sheet display contract and append checked Excel artifacts to the same run directory.
- `src/item_review_ui.py`: load one directory and auto-detect a complete same-directory workbook.
- `scripts/run_item_review_v2.py`: report the run directory and JSON, not HTML.
- `scripts/export_item_review_excel.py`: accept one completed run directory and append the workbook there.
- `scripts/item_review_app.py`: use one folder input and JSON/Excel downloads only.
- `scripts/build_item_review_excel.mjs`: update column styling, freeze panes, filters and render ranges for the reduced matrices.
- `tests/test_item_review_service.py`: JSON-only publication, legacy receipt compatibility and fail-closed boundaries.
- `tests/test_item_review_excel.py`: single-directory export and exact simplified workbook contract.
- `tests/test_item_review_ui.py`: one-input screen, optional same-directory Excel and no HTML.
- `README.md`, `TODO.md`, `docs/migration/2026-09-11-item-observation-service_kr.md`, `docs/migration/2026-09-11-item-excel-ui_kr.md`: current commands, artifacts and migration boundary.

## Task 1: Publish JSON-only observations with legacy read compatibility

**Files:**
- Modify: `tests/test_item_review_service.py`
- Modify: `src/item_review_service.py`
- Modify: `scripts/run_item_review_v2.py`

- [ ] **Step 1: Write failing tests for the new artifact contract**

Change the successful-run assertion and add an explicit absence assertion:

```python
receipt = service.run_item_review(request)
assert set(receipt['artifacts']) == {'item_observation.json'}
assert not (request.output_dir / 'item_review.html').exists()
```

Replace HTML mutation/publication cases with `item_observation.json` and receipt-boundary mutations. Add a legacy fixture by creating `item_review.html`, adding its SHA-256 to a copied completion receipt, and assert that `read_completed_item_review()` still returns 14 items.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_item_review_service.py -q
```

Expected: failures show that new runs still publish `item_review.html` and the reader requires both artifacts.

- [ ] **Step 3: Remove HTML from new publication and allow only the two explicit receipt shapes**

In `run_item_review`, remove the renderer import/call/write. Set `expected` to the JSON artifact only:

```python
expected = {output / 'item_observation.json': json_text.encode('utf-8')}
```

In `read_completed_item_review`, validate the artifact set before opening any named path:

```python
artifacts = receipt.get('artifacts')
_require(isinstance(artifacts, dict), 'invalid completed artifacts')
names = set(artifacts)
_require(names in ({'item_observation.json'},
                   {'item_observation.json', 'item_review.html'}),
         'unexpected completed artifacts')
```

This permits archived runs only; new runs never call the HTML renderer. Update the docstring accordingly. In `scripts/run_item_review_v2.py`, print `item_observation.json` instead of `item_review.html`.

- [ ] **Step 4: Run the focused tests and confirm GREEN**

Run the same command. Expected: all `test_item_review_service.py` tests pass, including JSON-only new runs and legacy JSON+HTML reads.

- [ ] **Step 5: Commit the observation boundary**

```powershell
git add -- src/item_review_service.py scripts/run_item_review_v2.py tests/test_item_review_service.py
git commit -m "refactor: stop publishing item review HTML"
```

## Task 2: Simplify the Excel contract and write into the completed run directory

**Files:**
- Modify: `tests/test_item_review_excel.py`
- Modify: `src/item_review_excel.py`
- Modify: `scripts/export_item_review_excel.py`
- Modify: `scripts/build_item_review_excel.mjs`

- [ ] **Step 1: Write failing contract tests for Summary and evidence columns**

Assert the exact matrices:

```python
summary, items, evidence = api.build_item_excel_view(report())['sheets']
assert len(summary['rows']) == 11
assert summary['rows'][-1][:2] == ['검토 대상', 'PDF 파일']
assert not any('SHA256' in str(value) or '추출 결과 위치' == value
               for row in summary['rows'] for value in row)
assert items['headers'] == [
    '고정 항목 키', '기준 문구', '검토 판정', '설명', '검토 메모',
    '원장 모델 조건 제안', '원장 제안 근거', '원장 검토 메모',
]
assert evidence['headers'] == [
    '고정 항목 키', '근거 종류', '현재 원문', '현재 노드 ID', '태그 종류',
    'PDF 페이지', 'XML 경로', '상세 근거 JSON',
]
assert not any(str(value).startswith('E000')
               for sheet in (items, evidence) for row in sheet['rows'] for value in row)
```

Keep the assertions for 14 item rows, 26 evidence rows, exact current text, pages, XML paths and full evidence JSON. Assert the input report is unchanged.

- [ ] **Step 2: Write failing same-directory export tests**

Call the intended API without an output directory:

```python
completion = api.export_item_review_excel(
    completed_run, Path('node'), Path('modules'))
assert (completed_run / 'item_review.xlsx').is_file()
assert api.read_completed_item_excel(completed_run) == (
    completed_run / 'item_review.xlsx').read_bytes()
```

Add cases proving that an existing `item_review.xlsx`, any partial Excel artifact, or a second export fails without overwriting the completed observation files. Preserve publication-boundary mutation tests for observation receipt, workbook, view and Excel receipt.

- [ ] **Step 3: Run Excel tests and confirm RED**

```powershell
.venv/Scripts/python.exe -m pytest tests/test_item_review_excel.py -q
```

Expected: failures show the old 23-row Summary, report-local ID columns and required separate output directory.

- [ ] **Step 4: Implement the reduced view without report-local evidence IDs**

Build only the 11 visible Summary rows. Do not copy `pdf_sha256`, XML hash, paths, receipt fields or `master_source` into the workbook. They remain unchanged in the report JSON.

Append Item Results rows as:

```python
items.append([
    item['item_key'], item['required_text'], '검토 필요', item['description'], '',
    author['proposed_model_rule'], author['proposal_evidence'], author['reviewer_note'],
])
```

Append Source Evidence rows without `eid`:

```python
evidence.append([
    item['item_key'], kind, window['text'], '\n'.join(window['owner_ids']),
    '\n'.join(window['structure_types']), ', '.join(map(str, pages)),
    '\n'.join(paths), json.dumps(window, ensure_ascii=False, sort_keys=True),
])
```

Update widths and keep `freeze='B2'` for Item Results and Source Evidence so the stable item key stays visible while scrolling.

- [ ] **Step 5: Change exporter and reader to one directory**

Use these public signatures:

```python
def export_item_review_excel(run_dir: Path, node_executable: Path,
                             node_modules: Path) -> dict:
    output_dir = run_dir = Path(run_dir)

def read_completed_item_excel(run_dir: Path) -> bytes:
    output_dir = run_dir = Path(run_dir)
```

Require the observation directory to exist and validate it before writing. Exclusively create each Excel artifact; do not call `mkdir` and do not overwrite any existing artifact. Snapshot observation receipt/JSON, publish `item_excel_complete.json` last, and retain the existing rollback/failure-marker behavior.

Remove `--output` from `scripts/export_item_review_excel.py`. Its single positional directory is both source and destination. Update the success print to `args.run_dir / 'item_review.xlsx'`.

- [ ] **Step 6: Update Artifact Tool formatting and render ranges**

Adjust amber review-note formatting to the new column E, freeze one column on both detail sheets, and render:

```javascript
const previews = [
  ['Summary', 'A1:C12', 'summary.png'],
  ['Item Results', 'A1:H7', 'items.png'],
  ['Source Evidence', 'A1:H4', 'evidence.png'],
];
```

Keep one recalculation, full error scan, filter buttons and exclusive XLSX publication.

- [ ] **Step 7: Run Excel tests and confirm GREEN**

Run the focused test command. Expected: all tests pass; real Artifact Tool tests may skip only when their explicit environment variables are absent.

- [ ] **Step 8: Commit the Excel boundary**

```powershell
git add -- src/item_review_excel.py scripts/export_item_review_excel.py scripts/build_item_review_excel.mjs tests/test_item_review_excel.py
git commit -m "feat: keep item workbook with its review run"
```

## Task 3: Use one folder in the local viewer and remove HTML

**Files:**
- Modify: `tests/test_item_review_ui.py`
- Modify: `src/item_review_ui.py`
- Modify: `scripts/item_review_app.py`

- [ ] **Step 1: Write failing loader tests**

Assert one-argument loading and automatic workbook discovery:

```python
screen = api.load_item_review_screen(completed)
assert set(screen) == {'report', 'json_bytes', 'excel_bytes'}
assert screen['excel_bytes'] is None

fake.read_completed_item_excel = lambda folder: b'checked excel'
(completed / 'item_excel_complete.json').write_text('{}', encoding='utf-8')
assert api.load_item_review_screen(completed)['excel_bytes'] == b'checked excel'
```

Add a partial-export case: any Excel view/workbook/failure marker without a valid completion receipt must fail closed rather than silently hide the problem. Keep mutation checks for JSON, observation receipt and completed Excel bytes.

- [ ] **Step 2: Write failing AppTest expectations**

Assert exactly one text input, JSON-only download before Excel exists, JSON+Excel downloads after a completed same-directory export, no HTML label, and no stale results after file mutation:

```python
assert len(app.text_input) == 1
assert [button.label for button in app.get('download_button')] == ['JSON 다운로드']
assert not any('HTML' in button.label for button in app.get('download_button'))
```

- [ ] **Step 3: Run UI tests and confirm RED**

```powershell
.venv/Scripts/python.exe -m pytest tests/test_item_review_ui.py -q
```

Expected: failures show the old two-folder input, HTML bytes and HTML download.

- [ ] **Step 4: Implement same-directory discovery and downloads**

Change the loader signature to:

```python
def load_item_review_screen(run_dir: Path) -> dict:
```

Snapshot and validate the observation receipt and JSON. If no Excel-related files exist, return `excel_bytes=None`. If `item_excel_complete.json` exists, call `read_completed_item_excel(run_dir)` twice around snapshots. If only partial Excel files or `item_excel_failed.json` exist, raise a controlled `ValueError`.

In the Streamlit app, remove `excel_text`, use the run path as the sole session key, remove HTML download, and defer JSON/Excel reads through `load_item_review_screen(run_dir)`. Display `Excel이 아직 생성되지 않았습니다.` when the checked workbook is absent.

- [ ] **Step 5: Run UI tests and confirm GREEN**

Run the focused UI command. Expected: all loader and AppTest cases pass with one folder field and no HTML exposure.

- [ ] **Step 6: Commit the UI boundary**

```powershell
git add -- src/item_review_ui.py scripts/item_review_app.py tests/test_item_review_ui.py
git commit -m "refactor: load item results from one folder"
```

## Task 4: Update user documentation and produce a fresh unified sample

**Files:**
- Modify: `README.md`
- Modify: `TODO.md`
- Modify: `docs/migration/2026-09-11-item-observation-service_kr.md`
- Modify: `docs/migration/2026-09-11-item-excel-ui_kr.md`
- Create during verification, not in Git: `outputs/item_review_zc_20260913_unified/`

- [ ] **Step 1: Update commands and artifact descriptions**

Document the two commands against the same directory:

```powershell
.venv/Scripts/python.exe -m scripts.run_item_review_v2 'samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf' --output outputs/my_item_review_001 --bundle outputs/review_service_zc_20260911_r2/extraction
.venv/Scripts/python.exe -m scripts.export_item_review_excel outputs/my_item_review_001
```

State that the first command creates checked JSON and the second appends the workbook. Remove claims that HTML is generated or downloaded. Explain that hashes and paths remain in JSON while Summary ends at the PDF filename. Preserve the Node/Artifact Tool deployment limitation.

- [ ] **Step 2: Run focused tests with the real authoring backend**

Configure the paths returned by `load_workspace_dependencies`:

```powershell
$env:ITEM_REVIEW_NODE = 'C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
$env:ITEM_REVIEW_NODE_MODULES = 'C:/Users/bella/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
.venv/Scripts/python.exe -m pytest tests/test_item_review_service.py tests/test_item_review_excel.py tests/test_item_review_ui.py -q
```

Expected: all focused tests pass and both real XLSX integration cases run rather than skip.

- [ ] **Step 3: Generate a new unified real sample**

Use the verified ZC PDF and extraction bundle with a fresh path:

```powershell
.venv/Scripts/python.exe -m scripts.run_item_review_v2 `
  'samples/SUG_RAW/TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf' `
  --bundle 'outputs/review_service_zc_20260911_r2/extraction' `
  --output 'outputs/item_review_zc_20260913_unified'
.venv/Scripts/python.exe -m scripts.export_item_review_excel `
  'outputs/item_review_zc_20260913_unified'
```

Expected: the same folder contains `item_observation.json`, both completion receipts, display JSON and `item_review.xlsx`; it contains no `item_review.html`.

- [ ] **Step 4: Verify and render the saved workbook**

Use the builder's three current preview PNGs and inspect them. Confirm Summary is `A1:C12`, Item Results is 14 rows with eight columns, Source Evidence is 26 rows with eight columns, and no cell starts with an `E####` report-local ID. Confirm the JSON still contains current and master hashes/paths.

- [ ] **Step 5: Run the complete verification gate**

```powershell
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe -m compileall -q src tests scripts
.venv/Scripts/python.exe -m pip check
git diff --check
```

Expected: all tests pass, compileall is silent, pip reports no broken requirements, and diff check reports no whitespace errors.

- [ ] **Step 6: Commit documentation and final verification record**

```powershell
git add -- README.md TODO.md docs/migration/2026-09-11-item-observation-service_kr.md docs/migration/2026-09-11-item-excel-ui_kr.md
git commit -m "docs: explain unified item review outputs"
```

Record the actual test count and new sample path before committing. Do not merge, push, remove historical outputs or modify another worktree.

## Parallel work boundary

PDF extraction for unprocessed languages or buyers may proceed in `C:/Users/bella/image-extractor/.worktrees/xml-markdown-review` on branch `feature/xml-markdown-review` while this plan is implemented in `C:/Users/bella/image-extractor/.worktrees/xml-review-v2` on branch `codex/xml-review-v2`.

The extraction task may edit `samples/tagged_pdf_xml_poc/src/`, its extraction tests and outputs inside the XML worktree. This plan does not edit those extractor files. The item-output task edits only the files listed above. Both tasks must:

- use their own worktree and branch;
- use different output directories located inside their own worktree;
- avoid editing `metadata/checklist/` and `metadata/checklist_v2/` concurrently;
- avoid switching branches, merging or rebasing while either working tree has uncommitted changes;
- preserve each worktree's own `.venv` and `PYTHONPATH`;
- merge the extraction branch into v2 only after both sides are committed and their tests pass.

If the extraction task changes `src/item_review_*`, `scripts/item_review_*`, `tests/test_item_review_*`, the four documentation files above, or the shared checklist metadata, stop one side and coordinate before continuing. Otherwise the two tasks have no live filesystem conflict; any later Git merge conflict remains isolated until integration.
