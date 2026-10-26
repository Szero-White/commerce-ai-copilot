"""Local Ollama end-to-end smoke runner; records observed evidence, not invented scores.

Run AFTER setting LLM_PROVIDER=ollama, EMBEDDING_PROVIDER=ollama and indexing.
No network calls except the locally configured Ollama endpoint.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from app.config import ROOT, Settings
from app.storage import Store
from app.services import question_answer

CASES = (
    {"question":"What sizes are available for the custom print hoodie?", "expected_source":"POD-202"},
    {"question":"Can I return a personalized item because I changed my mind?", "expected_source":"POD-POL-201"},
    {"question":"Bàn Oak 120 kích thước bao nhiêu?", "expected_source":"PRD-101"},
    {"question":"Có giảm giá 90% không?", "expected_source":None},
    {"question":"quasar neutrino zyzzyva impossible", "expected_source":None},
)


def main():
    config = Settings()
    if config.llm_provider != "ollama" or config.embedding_provider != "ollama":
        print("Set LLM_PROVIDER=ollama and EMBEDDING_PROVIDER=ollama first; did not claim live AI test.")
        return 2
    store=Store(config.data_path)
    docs=store.documents()
    indexed=sum(bool(d['embedding_json']) and d.get('embedding_model')==config.embedding_model for d in docs)
    if indexed != len(docs):
        print(f"Only {indexed}/{len(docs)} documents indexed for '{config.embedding_model}'. Run python -m scripts.index_embeddings.")
        return 2
    rows=[]
    for case in CASES:
        result=question_answer(store,config,case['question'])
        cited=[s['id'] for s in result['sources']]
        expected=case['expected_source']
        observed_pass=(result['mode']=='llm_rag_cited' and expected in cited) if expected else result['mode']=='no_evidence'
        rows.append({"question":case['question'],"expected_source":expected,"mode":result['mode'],
                     "retrieval_mode":result['retrieval_mode'],"retrieved_ids":cited,"retrieved_evidence":[{"id":src["id"],"title":src["title"],"excerpt":src["content"][:500]} for src in result["sources"]],
                     "latency_ms":result['latency_ms'],"tokens_in":result['tokens_in'],
                     "tokens_out":result['tokens_out'],"answer":result['answer'],"contract_pass":observed_pass,
                     "human_factuality_review":"NOT_COMPLETED"})
    report={"observed_at_utc":datetime.now(timezone.utc).isoformat(),"llm_model":config.ollama_model,
            "embedding_model":config.embedding_model,"document_count":len(docs),"model_calls_are_local":True,
            "contract_passed":sum(x['contract_pass'] for x in rows),"contract_total":len(rows),
            "disclaimer":"Checks mode/source IDs only; NOT verified factual accuracy, hallucination rate or production SLA.",
            "cases":rows}
    output=ROOT/'reports'/'live_rag_report.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(f"Saved observed results: {output} | {report['contract_passed']}/{report['contract_total']} contract checks")
    print("Optional manual answer review: python -m scripts.review_live_report")
    return 0 if all(x['contract_pass'] for x in rows) else 1


if __name__=='__main__':
    raise SystemExit(main())
