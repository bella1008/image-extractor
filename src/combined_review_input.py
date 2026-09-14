"""Prepare local UI input without creating or overwriting any result files."""
from datetime import datetime
import os
from pathlib import Path
from uuid import uuid4

from src.combined_review_run import CombinedReviewRequest
from src.review_service import ROOT


def prepare_combined_request(pdf_text: str, output_root: str) -> CombinedReviewRequest:
    pdf_text = pdf_text.strip().strip('"')
    if not pdf_text:
        raise ValueError('검토할 PDF 경로를 입력하세요.')
    pdf = Path(pdf_text)
    if not pdf.is_absolute():
        pdf = ROOT / pdf
    pdf = pdf.resolve()
    if not pdf.is_file() or pdf.suffix.lower() != '.pdf':
        raise ValueError('입력한 경로에서 PDF 파일을 찾을 수 없습니다.')
    output_root = output_root.strip().strip('"')
    if not output_root:
        raise ValueError('결과 저장 위치를 입력하세요.')
    root = Path(output_root)
    if not root.is_absolute():
        root = ROOT / root
    if root.exists() and not root.is_dir():
        raise ValueError('결과 저장 위치는 폴더여야 합니다.')
    node = os.environ.get('ITEM_REVIEW_NODE', '')
    modules = os.environ.get('ITEM_REVIEW_NODE_MODULES', '')
    if not node or not Path(node).is_file() or not modules or not Path(modules).is_dir():
        raise ValueError('Excel 작성 환경을 확인하세요: ITEM_REVIEW_NODE와 ITEM_REVIEW_NODE_MODULES 설정이 필요합니다.')
    folder = f'checklist_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:12]}'
    return CombinedReviewRequest(pdf, root.resolve() / folder, Path(node), Path(modules))
