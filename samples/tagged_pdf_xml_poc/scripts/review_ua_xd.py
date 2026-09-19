"""Generate fresh UA/XD XML review bundles; keep all human approvals pending."""
import argparse
from hashlib import sha256
from pathlib import Path
import subprocess

from review_sheet_rollout import STARTUP_CODE_HASHES, ROOT, prepare
from review_tk_xml import code_hashes, dump
from tagged_pdf_extractor.cli import _build_use_case

SOURCES = {
    'UA_ENG': ('TV_UA', 'BN68-26754A-00_SUG_Y26 TV ALL_UA_ENG_260520.0.pdf', ('ENG',)),
    'XD_INS': ('TV_XD', 'BN68-25031D-00_SUG_Y26 TV ALL_XD_INS_260113.0.pdf', ('INS',)),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    out = parser.parse_args().output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    mapping = ROOT / 'metadata/pdf_profile_mapping/pdf_profile_mapping.json'
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    runs = []
    for buyer, (folder, filename, languages) in SOURCES.items():
        source = ROOT / 'samples/SUG_RAW' / folder / filename
        if STARTUP_CODE_HASHES != code_hashes():
            raise RuntimeError('Runtime changed; use a fresh process and output')
        document, report, _ = _build_use_case(mapping).run(source, out / buyer)
        profile = document.readability_profile
        if (profile.source_token, profile.doc_type, profile.languages) != (buyer, 'A3', languages):
            raise ValueError('Source profile requires review')
        if STARTUP_CODE_HASHES != code_hashes():
            raise RuntimeError('Runtime changed during extraction')
        run = dict(buyer=buyer, pdf=str(source), sha256=sha256(source.read_bytes()).hexdigest(),
                   head=head, code_sha256=STARTUP_CODE_HASHES, source_token=buyer,
                   doc_type='A3', languages=languages, output=str(out / buyer), bookmarks=[])
        review = prepare(run)
        runs.append(run)
        dump(out / 'manifest.json', dict(head=head, runs=runs,
             canonical_profile_sha256=sha256(mapping.read_bytes()).hexdigest(), human_approval=False,
             previous_pending_human_buyers=['MENA', 'XL', 'XT', 'TK', 'ZW', 'PY', 'SQ_MI']))
        print(buyer, report.status, [k for k, v in review['hard_gates'].items() if not v], flush=True)


if __name__ == '__main__':
    main()
