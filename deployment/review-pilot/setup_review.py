"""Install this pilot's dependencies in its own Python 3.12 environment."""
import subprocess
import sys
import venv

from pilot_support import ROOT, verify_release


def main():
    verify_release()
    environment = ROOT / '.venv'
    python = environment / 'Scripts/python.exe'
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    if not python.is_file():
        raise ValueError('Incomplete .venv. Extract the ZIP into a new folder and run setup again.')
    subprocess.run([str(python), '-c', 'import sys; assert sys.version_info[:2] == (3, 12)'], check=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements-review-ui.txt')],
                   cwd=ROOT, check=True)
    subprocess.run([str(python), '-m', 'pip', 'check'], cwd=ROOT, check=True)
    subprocess.run([str(python), str(ROOT / 'start_review.py'), '--check'], cwd=ROOT, check=True)
    print('Setup complete. Double-click start.cmd.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Setup failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
