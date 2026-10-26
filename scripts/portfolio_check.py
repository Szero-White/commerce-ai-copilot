"""Repeatable offline portfolio acceptance run. Does not connect to an AI model.

Requires pip install -r requirements-dev.txt; does not need an app server.
All cases use a fresh temporary database and synthetic fixture documents.
"""
import json
import tempfile
import time
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from fastapi.testclient import TestClient
from app.config import Settings, ROOT
from app.main import create_app


def main():
    start = time.perf_counter()
    cases = []
    with tempfile.TemporaryDirectory() as directory:
        config = replace(Settings(), data_path=Path(directory)/'acceptance.db',
                         llm_provider='off', embedding_provider='off')
        with TestClient(create_app(settings=config)) as api:
            def check(name, ok, details):
                cases.append({'name': name, 'passed': bool(ok), 'observation': details})
            health = api.get('/api/health').json()
            check('Seeded knowledge base', health['documents'] >= 10,
                  {'documents': health['documents'], 'llm_provider': health['llm_provider']})
            known = api.post('/api/chat', json={'question': 'Bàn Oak 120 kích thước bao nhiêu?'}).json()
            check('Extractive answer with source', known['mode'] == 'extractive_demo' and
                  'PRD-101' in [s['id'] for s in known['sources']],
                  {'mode': known['mode'], 'sources': [s['id'] for s in known['sources']]})
            unknown = api.post('/api/chat', json={'question': 'quasar neutrino zyzzyva impossible'}).json()
            check('Unknown question abstains', unknown['mode'] == 'no_evidence' and not unknown['sources'],
                  {'mode': unknown['mode']})
            ticket = api.post('/api/support/triage', json={
                'message': 'My personalized mug arrived damaged. Can I get a refund?'}).json()
            check('Damaged item escalates to human', ticket['intent'] == 'damaged_product' and
                  ticket['priority'] == 'high' and ticket['autonomous_action'] is False and
                  ticket['status'] == 'DRAFT_REQUIRES_HUMAN_REVIEW',
                  {'intent': ticket['intent'], 'priority': ticket['priority'],
                   'evidence': [e['id'] for e in ticket['evidence']]})
            campaign = api.post('/api/campaign', json={'sku': 'PRD-101', 'audience': 'home office'}).json()
            check('Marketing remains draft-only', campaign['mode'] == 'template_preview' and
                  campaign['status'] == 'DRAFT_REQUIRES_HUMAN_APPROVAL',
                  {'mode': campaign['mode'], 'status': campaign['status']})
            agent = api.post('/api/agent', json={'task': 'Send an advert for PRD-101'}).json()
            check('Agent does not fake LLM usage', agent['mode'] == 'agent_disabled' and not agent['steps'],
                  {'mode': agent['mode']})
            eval_result = api.get('/api/evaluation').json()
            check('Retrieval evaluation has distinct negative set', eval_result['total'] >= 30 and
                  eval_result['negative_rejection']['total'] >= 30 and eval_result['score'] >= 0.9 and
                  eval_result['negative_rejection']['score'] >= 0.9,
                  {'hit_at_3': eval_result['score'], 'positive_passed': eval_result['passed'],
                   'positive_total': eval_result['total'], 'out_of_scope_passed':
                   eval_result['negative_rejection']['passed']})
            check('No public embedding write access',
                  api.post('/api/admin/index-embeddings').status_code == 403,
                  {'http_status': 403})
    result = {
        'release': '3.0.0', 'measured_utc': datetime.now(timezone.utc).isoformat(),
        'kind': 'offline_synthetic_api_acceptance', 'llm_used': False,
        'embeddings_used': False, 'paid_api_used': False,
        'disclaimer': ('Demonstrates local FastAPI and deterministic workflows only. '
                       'Does NOT verify generative RAG, model factuality, actual business ROI, or production safety.'),
        'cases': cases, 'passed': sum(1 for c in cases if c['passed']),
        'total': len(cases), 'elapsed_ms': round((time.perf_counter()-start)*1000),
    }
    output = ROOT/'reports'/'offline_acceptance_report.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"OFFLINE acceptance: {result['passed']}/{result['total']} passed | {output}")
    for case in cases:
        print(('PASS' if case['passed'] else 'FAIL') + ': ' + case['name'])
    return 0 if result['passed'] == result['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
