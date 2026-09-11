"""Export a completed observation's thin display view for format prototyping."""
import argparse
import hashlib
import json
from pathlib import Path

from src.review_report_view import build_report_view
from src.review_service import read_completed_observation


def prepare_view(run_dir: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f'use a fresh view file: {output}')
    completion = run_dir / 'review_complete.json'
    before = completion.read_bytes()
    view = build_report_view(read_completed_observation(run_dir))
    if completion.read_bytes() != before:
        raise ValueError('completion changed during view mapping')
    view['source_completion_sha256'] = hashlib.sha256(before).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(view, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
    return view


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare_view(args.run_dir, args.output)


if __name__ == '__main__':
    main()
