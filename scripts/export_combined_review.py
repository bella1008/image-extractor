"""Combine completed checklist/item observations into one fresh result folder."""
import argparse
from pathlib import Path

from src.combined_review_service import export_combined_review


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checklist_dir',type=Path)
    parser.add_argument('item_dir',type=Path)
    parser.add_argument('--output',type=Path,required=True,help='New result folder; existing folders are never overwritten')
    parser.add_argument('--node',type=Path,help='Optional developer Artifact Tool runtime')
    parser.add_argument('--node-modules',type=Path,help='Optional developer Artifact Tool dependencies')
    args=parser.parse_args(argv)
    if (args.node is None) != (args.node_modules is None):
        parser.error('Supply both --node and --node-modules, or omit both for Python')
    export_combined_review(args.checklist_dir,args.item_dir,args.output,args.node,args.node_modules)
    print(args.output/'review_report.xlsx')


if __name__=='__main__':
    main()
