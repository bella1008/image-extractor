"""Launch the item viewer only on this computer; never installs dependencies."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def _port(value):
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('port must be an integer from 1024 to 65535') from exc
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError('port must be between 1024 and 65535')
    return port


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run the read-only item viewer on localhost')
    parser.add_argument('--port', type=_port, default=8501)
    args = parser.parse_args(argv)
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    command = [sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'scripts/item_review_app.py'),
               '--server.address', '127.0.0.1', '--browser.gatherUsageStats', 'false',
               '--server.headless', 'true', '--server.port', str(args.port)]
    print(f'Open http://127.0.0.1:{args.port} in your browser. Stop with Ctrl+C.')
    return subprocess.run(command, cwd=ROOT, env=env).returncode


if __name__ == '__main__':
    raise SystemExit(main())
