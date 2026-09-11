"""Export the separate CHK-002 authoring workbook to a non-active JSON draft."""
import argparse
from pathlib import Path

from src.checklist_item_master import export_item_master


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('excel', type=Path)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--expected-seed-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export_item_master(args.excel, args.seed, args.output, expected_seed_sha256=args.expected_seed_sha256)


if __name__ == '__main__':
    main()
