"""Read-only, exact-revision XL dimensions/weight association audit.

Creates a review sidecar, never modifies semantic XML or inserts source text.
"""
import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import subprocess
from xml.etree import ElementTree as ET

import pymupdf


SOURCE_SHA = 'dce6f5417123809235904c6ce3e7a1ff32aadc57df0a28e2a74d2c676b15a849'


def text(node):
    return ' '.join(''.join(t.text or '' for t in node.iter('text')).split())


def compact(value):
    return ''.join(value.split())


def identity(node):
    return dict(object_ref=node.get('object-ref'),
                xml_path=node.get('source-structure-path'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    source = json.loads((bundle / 'review_document.json').read_text(encoding='utf8'))['source']
    pdf_path = Path(source['pdf'])
    assert sha256(pdf_path.read_bytes()).hexdigest() == SOURCE_SHA
    xml_path = bundle / 'semantic_document.xml'
    root = ET.parse(xml_path).getroot()
    table = next(n for n in root.iter('table') if n.get('object-ref') == '645 0 R')
    rows = table.findall('table_row')
    assert len(rows) == 18 and all(len(r.findall('table_cell')) == 4 for r in rows)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    pdf = pymupdf.open(pdf_path)
    page = pdf[1]
    lines = [dict(text=''.join(s['text'] for s in line['spans']), bbox=line['bbox'])
             for block in page.get_text('dict')['blocks'] for line in block.get('lines', [])]
    # The original ruled grid has a label column and three equally spaced value columns.
    # Restrict each source match by the actual PDF row and the value-column band.
    value_edges = (142.85, 238.65, 334.55, 430.276)
    records = []
    pictures = []
    for start in (0, 6, 12):
        models = rows[start].findall('table_cell')[1:]
        for offset, expected in ((4, 'Dimensions (W x H x D)'), (5, 'Weight')):
            row = rows[start + offset]
            cells = row.findall('table_cell')
            labels = cells[0].findall('paragraph')
            assert [text(n) for n in labels] == [expected, 'Without Stand', 'With Stand']
            label_lines = []
            for label in labels:
                box = tuple(map(float, next(label.iter('text')).get('bbox').split(',')))
                approximate_y = page.rect.height - box[1]
                matches = [line for line in lines
                           if compact(line['text']) == compact(text(label))
                           and line['bbox'][0] < value_edges[0]
                           and abs(line['bbox'][3] - approximate_y) < 4]
                assert len(matches) == 1, (text(label), matches)
                label_lines.append(matches[0])
            crop_name = f'row_{start + offset + 1}.png'
            rect = pymupdf.Rect(49, label_lines[0]['bbox'][1] - 3,
                               432, label_lines[-1]['bbox'][3] + 4)
            page.get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), clip=rect).save(output / crop_name)
            pictures.append((expected, crop_name))
            for column, cell in enumerate(cells[1:]):
                values = cell.findall('paragraph')
                assert len(values) == 2
                # A category heading has no value on its own baseline in the PDF.
                heading_y = sum(label_lines[0]['bbox'][1::2]) / 2
                assert not [line for line in lines
                            if value_edges[column] < line['bbox'][0] < value_edges[column + 1]
                            and abs(sum(line['bbox'][1::2]) / 2 - heading_y) < 2]
                for condition_index, value in enumerate(values):
                    label = labels[condition_index + 1]
                    label_line = label_lines[condition_index + 1]
                    center_y = sum(label_line['bbox'][1::2]) / 2
                    matches = [line for line in lines
                               if compact(line['text']) == compact(text(value))
                               and value_edges[column] < line['bbox'][0] < value_edges[column + 1]
                               and abs(sum(line['bbox'][1::2]) / 2 - center_y) < 2]
                    assert len(matches) == 1, (start, expected, column, text(value), matches)
                    records.append(dict(model_group=text(models[column]), property=expected,
                        condition=text(label), value=text(value), source_page=2,
                        source_row=start + offset + 1, source_column=column + 2,
                        model_source=identity(models[column]), property_source=identity(labels[0]),
                        condition_source=identity(label), value_source=identity(value),
                        pdf_condition_bbox=label_line['bbox'], pdf_value_bbox=matches[0]['bbox'],
                        crop=crop_name, source_literal_none=text(value) == 'None'))
    assert len(records) == 36
    assert Counter(r['condition'] for r in records) == {'Without Stand': 18, 'With Stand': 18}
    assert sum(r['source_literal_none'] for r in records) == 10
    audit = dict(source_pdf=str(pdf_path), source_sha256=SOURCE_SHA,
        semantic_xml=str(xml_path), semantic_sha256=sha256(xml_path.read_bytes()).hexdigest(),
        start_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        scope='XL_ENG / A3 / ENG / dimensions and weight only',
        association_count=36, source_literal_none_count=10,
        fabricated_empty_values=0, pdf_position_and_text_verified=True,
        runtime_semantic_associations_implemented=False, human_approval=False,
        records=records)
    (output / 'associations.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf8')
    body = '<h1>XL 치수·중량 하위 조건 검토</h1><p>PDF 2페이지 · 9개 모델 열 묶음 · 36개 값의 원문 문구와 위치 대조 통과.</p>'
    body += '<p>Dimensions / Weight는 상위 항목입니다. Without Stand와 With Stand에 각각 값이 연결됩니다. '
    body += '[내용 없음]은 추가하지 않습니다. None 10개는 실제 원문 문자열이며 빈 값이나 0으로 바꾸지 않습니다.</p>'
    body += '<p>아래는 원문 근거를 대조해 만든 별도 검토표입니다. 현재 semantic XML에는 이 하위 조건 연결이 명시되어 있지 않아, 자동 사양 비교용 연결 규칙은 후속 구현 대상입니다.</p>'
    body += '<table><tr><th>모델 묶음</th><th>상위 항목</th><th>조건</th><th>원문 값</th><th>PDF 근거</th></tr>'
    for r in records:
        body += '<tr>' + ''.join('<td>' + escape(r[k]) + '</td>' for k in ('model_group', 'property', 'condition', 'value'))
        body += f'<td><a href="{r["crop"]}">행 {r["source_row"]} / 열 {r["source_column"]}</a></td></tr>'
    body += '</table><p><a href="associations.json">36개 대응과 XML 원문 경로</a></p>'
    for label, picture in pictures:
        body += f'<h2>{escape(label)}</h2><img src="{picture}" alt="PDF source row" style="max-width:100%">'
    (output / 'review.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:17px Arial;max-width:1200px;margin:32px auto;line-height:1.6}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:8px}th{background:#eef2f6}</style>' + body, encoding='utf8')
    print(json.dumps({k:v for k,v in audit.items() if k != 'records'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
