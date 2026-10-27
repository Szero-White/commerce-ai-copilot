"""HTTP API + static portfolio UI. Local-first demo, not a production auth system."""
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
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


class Question(BaseModel):
    question: str = Field(min_length=3,max_length=600)


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

    @app.post("/api/chat")
    def chat(body:Question):
        return question_answer(store,settings,body.question)

    @app.post("/api/campaign")
    def campaign(body:Campaign):
        try:
            return campaign_draft(store,settings,body.sku,body.audience)
        except ValueError as e:
            raise HTTPException(status_code=404,detail=str(e)) from e

    @app.post("/api/support/triage")
    def support_triage(body:SupportRequest):
        return triage_message(store, settings, body.message)

    @app.post("/api/agent")
    def agent(body:AgentTask):
        return run_agent(store,settings,body.task)

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
