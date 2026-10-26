"""Human annotation of ACTUAL Ollama outputs; no extra model/API calls.

Operator rates answer factuality against the passages stored in the report.
This does not make the labels objective ground truth or certify production use.
"""
import json
from pathlib import Path
from app.config import ROOT

VALID = {'supported', 'unsupported', 'uncertain'}


def summarize_review(report: dict) -> dict:
    cases = report.get('cases', [])
    scored = [case.get('human_factuality_review') for case in cases]
    completed = sum(item in VALID for item in scored)
    return {'reviewed': completed, 'total': len(cases),
            'supported': sum(item == 'supported' for item in scored),
            'unsupported': sum(item == 'unsupported' for item in scored),
            'uncertain': sum(item == 'uncertain' for item in scored),
            'note': 'Human judgements on a tiny synthetic case set, NOT a production accuracy estimate.'}


def review_file(path: Path, ask=input, show=print) -> dict:
    if not path.is_file():
        raise FileNotFoundError('First run python -m scripts.verify_live_rag with real local Ollama')
    report = json.loads(path.read_text(encoding='utf-8'))
    if not report.get('model_calls_are_local') or not report.get('cases'):
        raise ValueError('This is not a validated live-model report format')
    for idx, case in enumerate(report['cases'], 1):
        show(f"\n[{idx}/{len(report['cases'])}] {case['question']}\n"
             f"Mode: {case['mode']} | sources: {case['retrieved_ids']}\n"
             f"Answer: {case['answer']}\n")
        show('Compare to the actual retrieved documents in the application; a valid source ID is not enough.')
        raw = ask('Label: [s]upported / [u]nsupported / [?] uncertain / [q]uit: ').strip().lower()
        if raw == 'q':
            break
        chosen = {'s': 'supported', 'u': 'unsupported', '?': 'uncertain'}.get(raw)
        if chosen is None:
            show('Invalid label, leaving this case unreviewed.')
            continue
        case['human_factuality_review'] = chosen
        case['human_review_notes'] = ask('Brief evidence/reason (or Enter to skip): ').strip()[:400]
    report['human_review_summary'] = summarize_review(report)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    show(f"Saved: {path} | reviewed {report['human_review_summary']['reviewed']}/{report['human_review_summary']['total']}")
    return report


if __name__ == '__main__':
    review_file(ROOT / 'reports' / 'live_rag_report.json')
