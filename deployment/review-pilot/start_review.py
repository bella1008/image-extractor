"""Check or start the locally installed combined reviewer UI."""
import argparse
import subprocess
import sys

from pilot_support import ROOT, verify_release, check_runtime


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check this interpreter and release without starting a server')
    parser.add_argument('--port', type=int, default=8501)
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error('port must be between 1024 and 65535')
    verify_release()
    if args.check:
        check_runtime()
        print('Ready: ZC_L02 ENG checklist pilot; automatic business decisions are not evaluated.')
        return 0
    python = ROOT / '.venv/Scripts/python.exe'
    if not python.is_file():
        raise ValueError('Run setup.cmd first.')
    subprocess.run([str(python), str(ROOT / 'start_review.py'), '--check'], cwd=ROOT, check=True)
    return subprocess.run([str(python), '-m', 'scripts.start_item_review_ui', '--combined',
                           '--open-browser', '--port', str(args.port)], cwd=ROOT).returncode


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'Cannot start review: {exc}', file=sys.stderr)
        raise SystemExit(1)
