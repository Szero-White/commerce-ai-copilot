"""The live verification script must refuse to run (and claim nothing) without a real Ollama."""
from dataclasses import replace

from app.config import Settings
from scripts import verify_live_rag


def test_live_script_refuses_when_providers_are_off(monkeypatch, capsys):
    monkeypatch.setattr(verify_live_rag, 'Settings', lambda: replace(Settings(), llm_provider='off', embedding_provider='off'))
    assert verify_live_rag.main() == 2
    assert 'did not claim live AI test' in capsys.readouterr().out


def test_live_script_refuses_when_ollama_unreachable(monkeypatch, capsys):
    monkeypatch.setattr(verify_live_rag, 'Settings', lambda: replace(
        Settings(), llm_provider='ollama', embedding_provider='ollama', ollama_url='http://127.0.0.1:9'))
    assert verify_live_rag.main() == 2
    assert 'not reachable' in capsys.readouterr().out


def test_live_script_refuses_when_models_missing(monkeypatch, capsys):
    monkeypatch.setattr(verify_live_rag, 'Settings', lambda: replace(Settings(), llm_provider='ollama', embedding_provider='ollama'))
    monkeypatch.setattr(verify_live_rag, 'list_models', lambda settings: ['tiny:1b'])
    assert verify_live_rag.main() == 2
    assert 'not installed' in capsys.readouterr().out
