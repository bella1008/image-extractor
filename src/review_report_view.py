"""Thin presentation mapping for report formats, independent of XLSX libraries."""
from collections import Counter

CHECKLIST_COLUMNS = ('scope', 'exclude_scope', 'common_id', 'check_id', 'section_heading', 'language',
                     'required_text', 'evidence_excerpt', 'result', 'observation', 'reason', 'pdf_pages',
                     'evidence_ids', 'reviewer_note')
EVIDENCE_COLUMNS = ('evidence_id', 'check_id', 'evidence_kind', 'composition_method', 'language',
                    'pdf_pages', 'required_fragment', 'text', 'source_node_ids', 'xml_paths', 'caveats')
EXCLUDED_COLUMNS = ('check_id', 'common_id', 'language', 'scope', 'exclude_scope', 'approval_status', 'status', 'reason')


def build_report_view(report: dict) -> dict:
    if report.get('schema_version') != 'checklist-observation/2' or report.get('decision_status') != 'not_evaluated':
        raise ValueError('expected an unevaluated observation schema 2')
    checklist, evidence, excluded = [], [], []
    for row in report['rows']:
        if row['status'] not in ('needs_review', 'not_applicable', 'excluded') or row['migration_status'] not in ('pending', 'excluded'):
            raise ValueError('unexpected business decision or migration activation')
        source = row['source_rule']
        if row['status'] != 'needs_review':
            excluded.append({key: row.get(key, source.get(key, '')) for key in EXCLUDED_COLUMNS})
            continue
        refs, pages = [], set()

        def add_evidence(item, kind, fragment=''):
            ref = f"{row['check_id']}:{len(refs)+1}"
            item_pages = sorted({e['page_index'] + 1 for p in item['parts'] for e in p['evidence'] if type(e.get('page_index')) is int})
            pages.update(item_pages)
            refs.append(ref)
            evidence.append({'evidence_id': ref, 'check_id': row['check_id'], 'evidence_kind': kind,
                             'composition_method': item.get('method', 'strict_unit'), 'language': item['language'],
                             'pdf_pages': ', '.join(map(str, item_pages)), 'required_fragment': fragment,
                             'text': item['text'], 'source_node_ids': '\n'.join(dict.fromkeys(p['node_id'] for p in item['parts'])),
                             'xml_paths': '\n'.join(dict.fromkeys(e['xml_path'] for p in item['parts'] for e in p['evidence'])),
                             'caveats': '; '.join(item.get('caveats', ['provisional_scope_and_role_require_review']))})
        for item in row['matches']:
            add_evidence(item, 'strict')
        for item in row['candidate_matches']:
            add_evidence(item, 'candidate')
        fragments = row.get('fragment_observations')
        if fragments:
            for fragment in fragments['fragments']:
                for item in fragment['candidates']:
                    add_evidence(item, 'fragment', fragment['required_text'])
        observation = ('strict_evidence' if row['matches'] else 'structure_candidate' if row['candidate_matches']
                       else 'distributed_fragments' if refs else 'unresolved')
        whole = row['matches'] or row['candidate_matches']
        checklist.append({'scope': source['scope'], 'exclude_scope': source['exclude_scope'],
                          'common_id': row['common_id'], 'check_id': row['check_id'],
                          'section_heading': source['legacy_section_heading'], 'language': source['language'],
                          'required_text': source['required_text'],
                          'evidence_excerpt': '\n\n'.join(item['text'] for item in whole),
                          'result': 'needs_review', 'observation': observation,
                          'reason': row['candidate_reason'] if not whole else 'provisional_scope_and_role_require_review',
                          'pdf_pages': ', '.join(map(str, sorted(pages))), 'evidence_ids': '\n'.join(refs), 'reviewer_note': ''})
    return {'schema_version': 'review-report-view/1', 'decision_status': 'not_evaluated', 'context': report['context'],
            'summary': {'rule_count': len(report['rows']), 'applicable_count': len(checklist), 'excluded_count': len(excluded),
                        'evidence_count': len(evidence), 'by_observation': dict(Counter(r['observation'] for r in checklist))},
            'columns': {'checklist': CHECKLIST_COLUMNS, 'evidence': EVIDENCE_COLUMNS, 'excluded': EXCLUDED_COLUMNS},
            'checklist': checklist, 'evidence': evidence, 'excluded': excluded}
