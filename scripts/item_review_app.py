"""Read-only local viewer for an explicitly selected completed item review."""
from functools import partial
from pathlib import Path

import streamlit as st

from src.item_review_ui import load_item_review_screen


def _download(run_dir, field):
    # Streamlit invokes deferred data at click time, not when drawing the button.
    return load_item_review_screen(run_dir)[field]


def main():
    st.set_page_config(page_title='구성품 항목별 검토', layout='wide')
    st.title('구성품 항목별 검토')
    st.text('완료된 관찰 결과를 읽습니다. 모든 항목은 검토 필요이며 모델 적용은 미확정입니다.')
    run_text = st.text_input('완료된 관찰 결과 폴더', key='item_run_path').strip()
    requested = run_text
    if st.session_state.get('loaded_item_paths') != requested:
        st.session_state.pop('loaded_item_paths', None)
    if st.button('불러오기', key='load_items', type='primary'):
        if run_text:
            st.session_state['loaded_item_paths'] = requested
        else:
            st.error('완료된 관찰 결과 폴더를 입력하세요.')
    if 'loaded_item_paths' not in st.session_state:
        st.info('폴더를 입력한 후 불러오기를 누르세요.')
        return
    run_dir = Path(run_text).resolve()
    try:
        screen = load_item_review_screen(run_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.session_state.pop('loaded_item_paths', None)
        # Exception text may contain untrusted paths; never render it as Markdown.
        st.error('결과를 검증하지 못했습니다. 현재 화면과 다운로드를 사용할 수 없습니다.')
        st.text(str(exc))
        return
    report = screen['report']
    st.subheader('검토 대상 PDF')
    st.text(report['target_source']['pdf_filename'])
    columns = st.columns(3)
    for column, key, label in zip(columns, ('item_count', 'needs_review', 'found'),
                                  ('하위 항목', '검토 필요', '단일 문구 근거'), strict=True):
        column.metric(label, report['summary'][key])
    st.dataframe([{'item_key': item['item_key'], 'required_text': item['required_text'],
                   '검토 판정': '검토 필요', '설명': item['description']}
                  for item in report['items']], hide_index=True, width='stretch')
    st.subheader('현재 문서의 상세 근거')
    for index, item in enumerate(report['items'], 1):
        # Expander labels support Markdown; keep labels fixed and source text inside.
        with st.expander(f'항목 {index} — 현재 문서 근거'):
            st.text(item['item_key'])
            st.text(item['required_text'])
            st.text('모델 적용: unknown / 조건 검증: unverified / 결과: needs_review')
            st.text('현재 문서의 항목 원문 · 노드 ID · 태그 · 페이지 · XML 위치')
            st.json(item['candidates'])
            st.text('현재 문서의 조건 안내 후보')
            st.json(item['condition_candidates'])
            st.text('담당자 제안 — 모델 조건으로 자동 실행하지 않습니다.')
            st.json(item['author_proposal'])
    st.subheader('검증된 결과 다운로드')
    for label, field, name, mime in (
        ('JSON 다운로드', 'json_bytes', 'item_observation.json', 'application/json'),
        ('Excel 다운로드', 'excel_bytes', 'item_review.xlsx',
         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
    ):
        if screen[field] is not None:
            st.download_button(label, data=partial(_download, run_dir, field),
                               file_name=name, mime=mime, key=field, on_click='rerun')
    if screen['excel_bytes'] is None:
        st.info('Excel이 아직 생성되지 않았습니다.')


if __name__ == '__main__':
    main()
