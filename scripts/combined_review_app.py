"""Read-only local viewer for one checked combined report folder."""
from functools import partial
from pathlib import Path

import streamlit as st

from src.combined_review_service import read_completed_combined_review
from src.combined_review_view import build_combined_review_view


def _download(run_dir, field):
    return read_completed_combined_review(run_dir)[field]


def main():
    st.set_page_config(page_title='매뉴얼 통합 검토', layout='wide')
    st.title('매뉴얼 통합 검토')
    st.text('일반 체크와 구성품 상세를 함께 확인합니다. 현재 결과는 검토 필요이며 자동 합격·불합격 판정은 아닙니다.')
    run_text = st.text_input('완료된 통합 결과 폴더', key='combined_run_path').strip()
    if st.session_state.get('loaded_combined_path') != run_text:
        st.session_state.pop('loaded_combined_path', None)
    if st.button('불러오기', key='load_combined', type='primary'):
        if run_text:
            st.session_state['loaded_combined_path'] = run_text
        else:
            st.error('완료된 통합 결과 폴더를 입력하세요.')
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
