# XL dimensions and weight association review

Source: `BN68-25031J-00_SUG_Y26 TV ALL_XL_ENG_260306.0.pdf`, XL_ENG / A3 / ENG, PDF page 2.
Starting branch: `feature/xml-markdown-review`; clean starting HEAD: `339385db91c04c3a3d454dcb662c19ccd46b503c`.

The PDF has six dimensions/weight rows across three model groups, with three model columns per group. Each label cell contains a category title followed by Without Stand and With Stand. Each value cell has two values aligned with those conditions. No value belongs to the category-title baseline.

All 36 values were matched to independently extracted PDF lines by text, column, and vertical position. Six newly rendered PDF row crops were visually inspected. The ten literal `None` values are printed in the PDF; they must remain strings, not become zero, null, or fabricated missing-content labels.

Example: UA50M**H has dimensions Without Stand = 111.08 x 64.38 x 8.64 cm and With Stand = None; weight Without Stand = 8.8 kg and With Stand = None.

The current semantic XML preserves the row/cell/paragraph order but does not explicitly encode property-condition-value associations. This review creates a separate evidence sidecar, not a runtime implementation. A future automatic spec comparison must consume verified explicit associations, rather than align paragraphs by their unadjusted indexes. Do not insert `[내용 없음]` into source text. A display-only empty category baseline, or explicit condition subrows, can express the hierarchy without inventing source values.

Existing contact-heading emphasis, contact paragraph breaks, screen-dims sentence breaks, and first-column spec emphasis were already addressed in the readability follow-up; they were not changed here. XT issues are outside this XL-first review.

Reproduction (POC working directory):

```powershell
.venv\Scripts\python.exe scripts\review_xl_spec_associations.py outputs\xml_review_xl_xt_20260920_readability_final\XL_ENG outputs\xml_review_xl_20260920_spec_associations
```

Use a new output directory when rerunning. The script rejects a different PDF SHA and unexpected structure; its source coordinates and object reference are exact-revision audit details, not shared runtime rules or stable checklist keys. Output contains `review.html`, `associations.json`, and six PDF crops. The JSON retains source XML paths, object references, PDF coordinates, and source hashes.

Status: source correspondence verified; automatic semantic association remains open; XL human approval remains pending. No production extraction code, canonical metadata, DB, or prior output was modified.

Validation for this review: exact-source audit 36/36 values, six crops inspected; `python -m pytest tests/test_xl_sheet.py -q`: 14 passed; POC `python -m compileall -q src tests scripts`: exit 0; `git diff --check`: passed. The full extraction suite was not rerun because production extraction code was unchanged.
