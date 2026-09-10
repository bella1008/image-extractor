"""Fresh PDF -> XML -> ReviewDocument integration; not a checklist review service."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from src.xml_review_gate import ARTIFACT_NAMES, CONTRACT, EXTRACTOR_SHA256, require, sha256


def extractor_digest() -> str:
    import hashlib
    import tagged_pdf_extractor
    root = Path(tagged_pdf_extractor.__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


def extract_review_document(pdf_path: Path, run_dir: Path, mapping_path: Path):
    """Reserve a new directory, use the unchanged POC, then publish v2 JSON last."""
    run_dir = Path(run_dir)
    if run_dir.exists():
        raise FileExistsError(f"Use a new run directory: {run_dir}")
    from tagged_pdf_extractor.application.extract_document import ExtractDocument
    from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
    from tagged_pdf_extractor.infrastructure.json_profile_repository import JsonProfileRepository
    from tagged_pdf_extractor.infrastructure.output_bundle import OutputBundleWriter
    from tagged_pdf_extractor.infrastructure.pymupdf_baseline import PyMuPdfBaselineReader
    from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
    from src.semantic_xml_reader import read_review_bundle

    pdf_path, mapping_path = Path(pdf_path).resolve(), Path(mapping_path).resolve()
    before = (sha256(pdf_path.read_bytes()), sha256(mapping_path.read_bytes()), extractor_digest())
    require(before[2] == EXTRACTOR_SHA256, "unsupported extractor source version")
    run_dir.mkdir(parents=True, exist_ok=False)
    use_case = ExtractDocument(TaggedPdfReader(), PyMuPdfBaselineReader(), QualityEvaluator(),
                               OutputBundleWriter(), JsonProfileRepository(mapping_path))
    use_case.run(pdf_path, run_dir)
    after = (sha256(pdf_path.read_bytes()), sha256(mapping_path.read_bytes()), extractor_digest())
    require(before == after, "PDF, mapping or extractor changed during extraction")
    receipt = {"contract": CONTRACT, "pdf_sha256": before[0], "mapping_sha256": before[1],
               "extractor_sha256": before[2], "artifacts": {name: sha256((run_dir / name).read_bytes()) for name in ARTIFACT_NAMES}}
    document = read_review_bundle(run_dir, receipt, pdf_path=pdf_path, mapping_path=mapping_path)
    document_json = json.dumps(asdict(document), ensure_ascii=True, indent=2) + "\n"
    with (run_dir / "review_document.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(document_json)
    receipt["review_document_sha256"] = sha256((run_dir / "review_document.json").read_bytes())
    # The receipt is the final completion record. Failed runs retain extraction evidence only.
    with (run_dir / "review_run.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract XML and construct v2 review data (no checklist evaluation)")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mapping", type=Path, default=Path(__file__).resolve().parents[1] / "metadata/pdf_profile_mapping/pdf_profile_mapping.json")
    args = parser.parse_args()
    try:
        document = extract_review_document(args.pdf, args.output, args.mapping)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"XML review preparation failed: {exc}\n")
    print(f"ReviewDocument created: {sum(1 for _ in document.iter_nodes())} nodes; checklist not evaluated.")
    print(args.output / "review_document.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
