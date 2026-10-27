"""HTTP API + static portfolio UI. Local-first demo, not a production auth system."""
import json
import time
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import ROOT, Settings
from .storage import Store
from .services import question_answer, campaign_draft, evaluate_retrieval
from .agent import run_agent
from .ollama import ModelUnavailable, has_model, list_models
from .llm import PROVIDERS, embedding_enabled, llm_enabled, llm_info
from . import gemini
from .support import triage_message
from .documents import IngestError, ingest_document


class TurnContext(BaseModel):
    """The previous answer's `turn_context`, echoed back by the client. Untrusted: ids are looked up, not believed."""
    ids: list[str] = Field(default_factory=list,max_length=5)
    kind: Literal["single","list","clarify","none"]="none"


class Question(BaseModel):
    question: str = Field(min_length=3,max_length=600)
    turn_context: TurnContext | None = None


class AgentTask(BaseModel):
    task: str = Field(min_length=5,max_length=400)


class SupportRequest(BaseModel):
    message: str = Field(min_length=10, max_length=800)


class Campaign(BaseModel):
    sku: str = Field(min_length=4,max_length=50)
    audience: str = Field(min_length=3,max_length=120)


def create_app(data_path=None, settings=None):
    settings=settings or Settings()
    store=Store(Path(data_path) if data_path else settings.data_path)
    app=FastAPI(title="Commerce AI Lab",version="3.0.0",
        description="Portfolio demonstration of retrieval, opt-in LLM generation, drafts and evaluation.")
    app.state.store=store
    app.state.settings=settings
    app.mount("/assets", StaticFiles(directory=ROOT/"web"), name="assets")

    @app.get("/")
    def home():
        return FileResponse(ROOT/"web"/"index.html")

    @app.get("/api/health")
    def health(probe: bool=False):
        """Configuration only by default. ?probe=true also asks the configured provider(s) which models exist."""
        docs=store.documents()
        embedding_on=embedding_enabled(settings)
        result={"status":"ok","documents":len(docs),"llm_provider":settings.llm_provider,
                "embedding_provider":settings.embedding_provider,
                "llm":llm_info(settings),
                "vector_indexed":sum(bool(d["embedding_json"]) and d.get("embedding_model")==settings.embedding_model for d in docs),
                # Documents added or changed since the last `scripts.index_embeddings` run are searched by BM25 only.
                "vector_missing":(len(docs)-sum(bool(d["embedding_json"]) and d.get("embedding_model")==settings.embedding_model for d in docs)) if embedding_on else None,
                "corpus_version":store.corpus_version(),
                "embedding_model":settings.embedding_model if embedding_on else None,
                "simulation":True,"public_data_only":True}
        if probe and (llm_enabled(settings) or embedding_on):
            probes={}
            for provider in sorted({p for p in (settings.llm_provider,settings.embedding_provider) if p in PROVIDERS}):
                try:
                    installed=gemini.list_models(settings) if provider=="gemini" else list_models(settings)
                    probes[provider]={"reachable":True,
                        "llm_model_available":has_model(installed,settings.gemini_model if provider=="gemini" else settings.ollama_model) if settings.llm_provider==provider else None,
                        "embedding_model_available":has_model(installed,settings.embedding_model) if settings.embedding_provider==provider else None}
                except ModelUnavailable as exc:
                    probes[provider]={"reachable":False,"error":str(exc)[:200]}
            result["providers"]=probes
            if "ollama" in probes:
                result["ollama"]=probes["ollama"]  # kept for existing clients
        return result

    @app.get("/api/products")
    def products():
        return [{"id":d["id"],"title":d["title"],"content":d["content"]}
                for d in store.documents() if d["category"]=="product"]

    @app.get("/api/documents")
    def documents():
        return [{"id":d["id"],"title":d["title"],"category":d["category"],
                 "content":d["content"]} for d in store.documents()]

    def tracked(kind, work):
        """Run one pipeline request. A request that ends in an error is counted as failed (monitoring), then re-raised unchanged.

        Successful requests are logged by the pipeline itself (with mode, tokens and timings)."""
        start = time.perf_counter()
        try:
            return work()
        except Exception:
            store.log(kind, "error", round((time.perf_counter() - start) * 1000), ok=False)
            raise

    @app.post("/api/chat")
    def chat(body:Question):
        return tracked("chat", lambda: question_answer(
            store,settings,body.question,body.turn_context.model_dump() if body.turn_context else None))

    @app.post("/api/campaign")
    def campaign(body:Campaign):
        def work():
            try:
                return campaign_draft(store,settings,body.sku,body.audience)
            except ValueError as e:
                raise HTTPException(status_code=404,detail=str(e)) from e
        return tracked("campaign", work)

    @app.post("/api/support/triage")
    def support_triage(body:SupportRequest):
        return tracked("support_triage", lambda: triage_message(store, settings, body.message))

    @app.post("/api/agent")
    def agent(body:AgentTask):
        return tracked("agent", lambda: run_agent(store,settings,body.task))

    @app.post("/api/documents/upload")
    async def upload_document(request: Request, filename: str = Query(min_length=1, max_length=200)):
        """Ingest one .txt or text-based .pdf. The file is the raw request body and its name is the `filename` query
        parameter (no multipart dependency). Local demo only: switch off with DOC_UPLOAD_ENABLED=off."""
        start = time.perf_counter()

        def refuse(status, detail):
            store.log("ingest", "rejected", round((time.perf_counter() - start) * 1000), ok=False)
            raise HTTPException(status, detail)

        if not settings.doc_upload_enabled:
            refuse(403, "Tải tài liệu đang tắt (DOC_UPLOAD_ENABLED=off).")
        limit = settings.doc_max_upload_bytes
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            refuse(413, f"Tệp vượt giới hạn {limit // 1000} KB.")
        data = bytearray()
        async for part in request.stream():
            data += part
            if len(data) > limit:
                refuse(413, f"Tệp vượt giới hạn {limit // 1000} KB.")
        try:
            result = await run_in_threadpool(ingest_document, store, settings, filename, bytes(data))
        except IngestError as exc:
            refuse(exc.status, str(exc))
        store.log("ingest", "ok", round((time.perf_counter() - start) * 1000))
        return result

    @app.get("/api/documents/files")
    def document_files():
        return {"files": store.ingested_files(settings.embedding_model if embedding_enabled(settings) else None),
                "limits": {"extensions": [".txt", ".pdf"], "max_bytes": settings.doc_max_upload_bytes,
                           "max_pdf_pages": settings.doc_max_pdf_pages, "max_chunks": settings.doc_max_chunks,
                           "chunk_chars": settings.doc_chunk_chars, "chunk_overlap": settings.doc_chunk_overlap},
                "upload_enabled": settings.doc_upload_enabled, "ocr": False}

    @app.get("/api/evaluation")
    def evaluation():
        items=json.loads((ROOT/"data"/"eval_set.json").read_text(encoding="utf-8"))
        return evaluate_retrieval(store,settings,items)

    @app.get("/api/metrics")
    def metrics():
        return store.metrics()

    @app.post("/api/admin/index-embeddings",include_in_schema=False)
    def no_index():
        raise HTTPException(403,"Index via CLI: python -m scripts.index_embeddings (no public write API)")

    return app


app=create_app()
