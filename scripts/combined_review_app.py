"""Local checklist execution and checked report viewer."""
from functools import partial
from pathlib import Path

import streamlit as st

from src.combined_review_service import read_completed_combined_review
from src.combined_review_view import build_combined_review_view
from src.combined_review_input import prepare_combined_request
from src.combined_review_run import run_combined_review
from src.review_service import ROOT


def _download(run_dir, field):
    return read_completed_combined_review(run_dir)[field]


def main():
    st.set_page_config(page_title='매뉴얼 통합 검토', layout='wide')
    st.title('매뉴얼 통합 검토')
    st.caption('현재 제공: ZC 영어 체크리스트 검토 파일럿. 일반 체크와 구성품 상세의 통합 결과입니다. '
               'PDF 변경 비교·회사 사양 검토·다국어 참고 의견은 아직 포함되지 않습니다.')
    st.text('일반 체크와 구성품 상세를 함께 확인합니다. 현재 결과는 검토 필요이며 자동 합격·불합격 판정은 아닙니다.')
    pending = st.session_state.pop('new_combined_path', None)
    if pending:
        st.session_state['combined_run_path'] = pending
        st.session_state['loaded_combined_path'] = pending
        st.success('체크리스트 결과 파일을 생성했습니다. 아래에서 확인하고 다운로드하세요.')
    run_text = st.text_input('완료된 통합 결과 폴더', key='combined_run_path').strip()
    if st.session_state.get('loaded_combined_path') != run_text:
        st.session_state.pop('loaded_combined_path', None)
    if st.button('불러오기', key='load_combined', type='primary'):
        if run_text:
            st.session_state['loaded_combined_path'] = run_text
        else:
            st.error('완료된 통합 결과 폴더를 입력하세요.')
    with st.expander('PDF로 새 체크리스트 검토 실행', expanded=not run_text):
        pdf_text = st.text_input('검토할 PDF 경로', key='combined_pdf_path',
                                 help='탐색기에서 PDF의 경로를 복사해 붙여 넣으세요. 원래 파일명을 유지하세요.')
        output_root = st.text_input('결과 저장 위치', value=str(ROOT / 'outputs'), key='combined_output_root')
        st.caption('실행마다 이 위치에 새 폴더를 만듭니다. 완료될 때까지 이 화면에서 추가 조작을 하지 마세요.')
        if st.button('체크리스트 검토 실행', key='run_combined', type='primary'):
            st.session_state.pop('loaded_combined_path', None)
            request = None
            try:
                request = prepare_combined_request(pdf_text, output_root)
                st.text(f'이번 결과 폴더: {request.output_dir}')
                with st.spinner('PDF 추출과 체크리스트 근거 조사, Excel 생성을 진행하고 있습니다…'):
                    run_combined_review(request)
                    read_completed_combined_review(request.output_dir)
            except Exception as exc:
                st.error('검토를 완료하지 못했습니다. 완료된 결과로 제공하지 않습니다.')
                st.text(str(exc))
                if request is not None and request.output_dir.exists():
                    st.text(f'문제 확인용 폴더: {request.output_dir}')
                return
            st.session_state['new_combined_path'] = str(request.output_dir)
            st.rerun()
    if 'loaded_combined_path' not in st.session_state:
        st.info('결과 폴더를 입력한 후 불러오기를 누르세요.')
        return
    try:
        run_dir = Path(run_text).resolve()
        screen = read_completed_combined_review(run_dir)
        view = build_combined_review_view(screen['report'])
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        st.session_state.pop('loaded_combined_path', None)
        st.error('결과를 검증하지 못했습니다. 현재 화면과 다운로드를 사용할 수 없습니다.')
        st.text(str(exc))
        return
    report = screen['report']
    st.subheader('검토 대상 PDF')
    st.text(report['items']['target_source']['pdf_filename'])
    st.text(f"프로필: {report['checklist']['context']['source_token']} / 검토 언어: {report['checklist']['language']}")
    left, right = st.columns(2)
    left.metric('일반 체크리스트', report['summary']['parent_check_count'])
    right.metric('그중 구성품 상세', report['summary']['child_item_count'])
    st.caption('구성품 상세는 일반 체크의 하위 항목입니다. 두 숫자를 합산하지 않습니다.')
    st.download_button('통합 Excel 다운로드', data=partial(_download, run_dir, 'excel_bytes'),
                       file_name='review_report.xlsx',
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       key='combined_excel', on_click='rerun', type='primary')
    for sheet, title in zip(view['sheets'][1:3], ('일반 체크리스트', '구성품 상세'), strict=True):
        st.subheader(title)
        rows = [{label: value for label, value in zip(sheet['headers'], row, strict=True)
                 if label != '검토 메모'} for row in sheet['rows']]
        st.dataframe(rows, hide_index=True, width='stretch')
    st.caption('상세 근거는 Excel의 Source Evidence 시트에서 확인하세요. 메모는 다운로드한 사본에 작성하세요.')
    with st.expander('내부 확인용 데이터'):
        st.text('문제 조사나 결과 재현이 필요할 때 사용하는 JSON입니다.')
        st.download_button('내부 JSON 다운로드', data=partial(_download, run_dir, 'json_bytes'),
                           file_name='review_report.json', mime='application/json',
                           key='combined_json', on_click='rerun')


if __name__ == '__main__':
    main()
