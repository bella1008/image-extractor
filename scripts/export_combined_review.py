"""Combine completed checklist/item observations into one fresh result folder."""
import argparse
import os
from pathlib import Path

from src.combined_review_service import export_combined_review


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checklist_dir',type=Path)
    parser.add_argument('item_dir',type=Path)
    parser.add_argument('--output',type=Path,required=True,help='New result folder; existing folders are never overwritten')
    parser.add_argument('--node',type=Path,default=os.environ.get('ITEM_REVIEW_NODE'))
    parser.add_argument('--node-modules',type=Path,default=os.environ.get('ITEM_REVIEW_NODE_MODULES'))
    args=parser.parse_args()
    if args.node is None or args.node_modules is None:
        parser.error('Set ITEM_REVIEW_NODE and ITEM_REVIEW_NODE_MODULES, or pass --node and --node-modules')
    export_combined_review(args.checklist_dir,args.item_dir,args.output,args.node,args.node_modules)
    print(args.output/'review_report.xlsx')


if __name__=='__main__':
    main()
