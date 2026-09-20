"""Re-extract the approved representatives into a new, non-overwriting folder."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from tagged_pdf_extractor.cli import _build_use_case

ROOT = Path(__file__).resolve().parents[3]
SOURCES = {
    'ZC': 'TV_ZC/BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf',
    'ZG': 'TV_ZG/BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf',
    'AFRICA': 'TV_AFRICA/BN68-25031G-00_SUG_Y26 TV ALL_AFRICA_L05_251230.0.pdf',
    'CE': 'TV_CE/BN68-26318A-00_SUG_Y26 TV ALL_CE_L05_260422.0.pdf',
    'XU': 'TV_XU/BN68-24437C-01_SUG_Y26 TV ALL_XU_ENG_260129.0.pdf',
    'KR': 'TV_KR/BN68-25108A-00_SUG_Y26 TV ALL_KR_KOR_251218.0.pdf',
    'LATIN': 'TV_LATIN/BN68-24972A-00_SUG_Y26 TV ALL_LATIN_L02_250105.0.pdf',
}


def extract(buyer, output):
    source = ROOT / 'samples/SUG_RAW' / SOURCES[buyer]
    if not source.is_file() and buyer == 'CE':
        source = ROOT.parent / 'xml-extractor-release/samples/SUG_RAW' / SOURCES[buyer]
    document, report, _ = _build_use_case().run(source, output / buyer)
    profile = document.readability_profile
    return dict(buyer=buyer, pdf=str(source), sha256=sha256(source.read_bytes()).hexdigest(),
                pipeline_status=report.status, source_token=profile.source_token,
                doc_type=profile.doc_type, languages=profile.languages,
                bookmarks=[(b.source_title, b.start_page_index, b.end_page_index)
                           for b in document.bookmark_page_bounds],
                output=str((output / buyer).resolve()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    runs = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(extract, buyer, args.output) for buyer in SOURCES]):
            run = future.result()
            runs.append(run)
            print(run['buyer'], run['pipeline_status'], flush=True)
    manifest = dict(head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    git_status=subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True),
                    runs=sorted(runs, key=lambda run: run['buyer']))
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')


if __name__ == '__main__':
    main()
