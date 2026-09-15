"""Compare fresh representative bundles, preserving source identity and order."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
from types import SimpleNamespace
from xml.etree import ElementTree as E

import pymupdf as fitz
from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W

POC = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')


def text(node):
    return ''.join(t.text or '' for t in node.iter('text'))


def norm(value):
    return ''.join(value.split())


def fragments(root):
    return [(n.get('page-index'), n.get('mcid'), n.get('object-ref'), norm(n.text or ''))
            for n in root.iter('text')]


def source_signature(root, tags=None, display=False):
    return [(n.tag, n.get('object-ref'), n.get('display-role'), norm(text(n))) for n in root.iter()
            if (tags and n.tag in tags) or (display and n.get('display-role'))]


def prepare(before, output):
    manifest = read(output / 'manifest.json')
    legacy = POC / 'outputs/xml_review_cross_buyer_20260914_ownership_audit'
    rows = read(legacy / 'ownership_audit.json')['rows']
    ce_sources = read(POC / 'outputs/xml_review_ce_20260914_paragraph_review/source_cases.json')
    for index, (language, source) in enumerate(ce_sources.items()):
        for kind in ('power', 'fee'):
            rows.append(dict(buyer='CE', language=language, kind=kind,
                page=index * 8 + (2 if kind == 'power' else 8),
                target_text=source['power_continuation'] if kind == 'power' else source['fee_items'][0],
                pdf_crop=f'CE_{language}_{kind}.png',
                structural_status='pass'))
    summaries = []
    for run in manifest['runs']:
        buyer = run['buyer']
        folder = output / buyer
        old = before / buyer
        root = E.parse(folder / 'semantic_document.xml').getroot()
        previous = E.parse(old / 'semantic_document.xml').getroot()
        raw = E.parse(folder / 'raw_structure.xml').getroot()
        report = read(folder / 'extraction_report.json')
        prior_report = read(old / 'extraction_report.json')
        document = root.find('document')
        parents = {c:n for n in document.iter() for c in n}
        raw_parents = {c:n for n in raw.iter() for c in n}
        headings = W._resolve_heading_candidates(root, SimpleNamespace(heading_hierarchy=report['heading_hierarchy']))
        old_headings = W._resolve_heading_candidates(previous, SimpleNamespace(heading_hierarchy=prior_report['heading_hierarchy']))
        # List labels are rendered as Markdown markers; their source text is not body text.
        # Native bullets/decimal list counters are structural HTML markers and
        # absent from innerText. Keep source note/alphabetic labels (※, a), ...)
        # in the character oracle; excluding all labels would hide source loss.
        labels = [label for item in document.iter('list_item') for label in item.findall('label')]
        native_labels = [label for label in labels if norm(text(label)) in {'•', '–', '°', '¯', '\x80'}
                         or re.fullmatch(r'[0-9]+\.', norm(text(label)))]
        excluded = {t for label in native_labels for t in label.iter('text')}
        source_text = lambda n: ''.join(t.text or '' for t in n.iter('text') if t not in excluded)
        units = []
        def walk(n):
            if n.tag in ('attributes', 'label'):
                return
            children = [c for c in n if c.tag != 'attributes']
            if (n.tag in ('list', 'table') or children and all(c.tag in ('text', 'span', 'link', 'figure') for c in children)) and list(n.iter('text')):
                units.append(dict(text=source_text(n), markdown='\n\n'.join(W._render_element(n, headings)),
                                  source_path=n.get('source-structure-path'), object_ref=n.get('object-ref'),
                                  tag=n.tag, pages=sorted({int(t.get('page-index')) for t in n.iter('text')})))
                return
            for c in children:
                walk(c)
        walk(document)
        language_stats = {}
        signatures = report['metrics'].get('multilingual_heading_audit', {}).get('languages', [])
        for language_index, language in enumerate(run['languages']):
            if run['bookmarks']:
                start, end = run['bookmarks'][language_index][1:]
            elif len(run['languages']) > 1:
                start = end = language_index
            else:
                start, end = 0, 999
            def belongs(n):
                pages = {int(t.get('page-index')) for t in n.iter('text')}
                return pages and all(start <= p <= end for p in pages)
            nodes = [n for n in document.iter() if belongs(n)]
            common = next((s['heading_total'] for s in signatures if s['language'] == language), None)
            language_stats[language] = dict(
                page_range=[start + 1, end + 1] if end != 999 else 'whole PDF',
                audit_heading_count=common,
                heading_nodes_including_cover_and_display=sum(n in headings or n.tag == 'heading'
                    or n.get('display-role') == 'section-heading' for n in nodes),
                review_units=sum(bool(u['pages']) and all(start <= p <= end for p in u['pages']) for u in units),
                block_tags=dict(Counter(n.tag for n in nodes if n.tag in ('paragraph','list','list_item','table','figure','heading'))),
                tables=[dict(rows=len(n.findall('table_row')), cells=len(n.findall('.//table_cell')),
                             figures=len(list(n.iter('figure'))), object_ref=n.get('object-ref')) for n in nodes if n.tag == 'table'],
                display_roles=dict(Counter(n.get('display-role') for n in nodes if n.get('display-role'))))
        ownership = []
        for row in (r for r in rows if r['buyer'] == buyer):
            row = dict(row)
            if buyer == 'CE':
                candidates = [n for n in document.iter() if n.get('object-ref') and norm(text(n)) == norm(row['target_text'])
                              and {int(t.get('page-index')) for t in n.iter('text')} == {row['page'] - 1}]
                target = min(candidates, key=lambda n:len(list(n.iter())))
                row['object_ref'] = target.get('object-ref')
                shutil.copyfile(POC / 'outputs/xml_review_ce_20260914_paragraph_review' / f"{row['language']}_{row['kind']}_pdf.png", output / row['pdf_crop'])
            else:
                target = next(n for n in document.iter() if n.get('object-ref') == row['object_ref'])
                if buyer == 'AFRICA' and row['language'] == 'ARA' and row['kind'] == 'power':
                    # Original audit image had a manual left-column correction
                    # not reflected in its older JSON rectangle. Rechecked p35.
                    row['crop_rect'] = [42, 45, 230, 160]
                with fitz.open(run['pdf']) as pdf:
                    pdf[row['page'] - 1].get_pixmap(matrix=fitz.Matrix(2, 2), clip=fitz.Rect(row['crop_rect'])).save(output / row['pdf_crop'])
            row['target_text'] = text(target)
            if row['kind'] == 'power':
                passed = (target.get('display-role') == 'list-continuation' or
                          parents[target].tag == 'list_body' and parents[parents[target]].tag == 'list_item')
            else:
                source = next(n for n in raw.iter('element') if n.get('object-ref') == row['object_ref'])
                siblings = list(raw_parents[source])
                i = siblings.index(source)
                intro = next(n for n in document.iter() if n.get('object-ref') == siblings[i-1].get('object-ref'))
                second = next(n for n in document.iter() if n.get('object-ref') == siblings[i+1].get('object-ref'))
                passed = (parents[target].tag == parents[second].tag == 'list_item'
                          and parents[parents[target]] is parents[parents[second]]
                          and parents[parents[parents[target]]] is parents[intro])
                row.update(intro_text=text(intro), condition_texts=[text(target), text(second)])
                # Include both complete conditions, not just the first item's
                # bbox plus a fixed padding that can truncate a longer language.
                boxes = [tuple(map(float, t.get('bbox').split(',')))
                         for n in (intro, target, second) for t in n.iter('text') if t.get('bbox')]
                if boxes:
                    with fitz.open(run['pdf']) as pdf:
                        page = pdf[row['page'] - 1]
                        rect = fitz.Rect(min(b[0] for b in boxes)-8, page.rect.height-max(b[3] for b in boxes)-8,
                                         max(b[2] for b in boxes)+8, page.rect.height-min(b[1] for b in boxes)+38)
                        # Some tagged trailing fragments lack geometry. Include
                        # three source lines of context and visually verify the
                        # full second condition against the PDF crop.
                        row['crop_rect'] = list(rect)
                        page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect).save(output / row['pdf_crop'])
                elif buyer != 'CE':
                    raise ValueError(f'Missing complete fee crop evidence: {buyer}')
            row.update(before_status=row.pop('structural_status'), structural_status='pass' if passed else 'hard_gate_failed',
                       source_path=target.get('source-structure-path'), semantic_parent=parents[target].tag)
            ownership.append(row)
        old_display = source_signature(previous, display=True)
        new_display = source_signature(root, display=True)
        # Existing display hints must still address the same source units. Sentence
        # breaks within the two repaired power paragraphs may legitimately change.
        stable_display = lambda items:[i for i in items if i[2] != 'sentence-break-source']
        gates = dict(report['hard_gates'],
            raw_xml_byte_identical=(folder/'raw_structure.xml').read_bytes() == (old/'raw_structure.xml').read_bytes(),
            source_fragment_text_and_order=fragments(root) == fragments(previous),
            headings_unchanged=[(n.get('object-ref'), norm(text(n))) for n in headings] == [(n.get('object-ref'), norm(text(n))) for n in old_headings],
            tables_and_figures_unchanged=source_signature(root, ('table','figure')) == source_signature(previous, ('table','figure')),
            existing_display_targets_unchanged=stable_display(old_display) == stable_display(new_display),
            ownership_relations=all(r['structural_status']=='pass' for r in ownership))
        if buyer in ('CE', 'KR', 'LATIN'):
            gates['semantic_xml_byte_identical'] = (folder/'semantic_document.xml').read_bytes() == (old/'semantic_document.xml').read_bytes()
            gates['markdown_byte_identical'] = (folder/'semantic_document.md').read_bytes() == (old/'semantic_document.md').read_bytes()
        bundle = dict(source=run, scope='Targeted paragraph ownership regression, not a new full buyer translation approval',
                      statistics=language_stats, hard_gates=gates, ownership=ownership,
                      whole_document=dict(review_units=len(units), tables=len(list(document.iter('table'))),
                                          figures=len(list(document.iter('figure')))),
                      native_list_marker_counts=dict(Counter(norm(text(n)) for n in native_labels)),
                      status='pending_html_validation', before=str(old.resolve()),
                      display_delta=dict(before=old_display, after=new_display),
                      warnings=['Previously recorded PDF wording/editorial and image-only review notes remain unchanged.'])
        dump(folder/'review_document.json', bundle)
        dump(folder/'render_input.json', dict(source_text=source_text(document), units=units, ownership=ownership))
        summaries.append(dict(buyer=buyer, hard_gates=gates, statistics=language_stats,
                              ownership_count=len(ownership), failed=[k for k,v in gates.items() if not v]))
        print(buyer, 'gates', [k for k,v in gates.items() if not v], flush=True)
    dump(output/'review_summary.json', summaries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    prepare(args.before, args.output)
