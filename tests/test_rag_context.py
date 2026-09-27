"""Contexto RAG opcional — degradação graciosa e costura no analyst, sem rede."""

from types import SimpleNamespace

import agent.graph as G
from agent.graph import analyst_node
from agent.rag_client import fetch_rag_context


class _FakeStructured:
    def __init__(self) -> None:
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return SimpleNamespace(
            is_fatal=False,
            needs_research=False,
            search_queries=[],
            target_files=["a.py"],
            analysis="causa raiz: x",
        )


class _FakeLLM:
    def __init__(self) -> None:
        self.structured = _FakeStructured()

    def with_structured_output(self, cls):
        return self.structured


def _analyst_with_fake_llm(monkeypatch, tmp_path, rag_text: str):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr("agent.rag_client.fetch_rag_context", lambda q, top_k=5: rag_text)
    fake = _FakeLLM()
    monkeypatch.setattr(G, "get_llm", lambda *a, **k: fake)
    out = analyst_node(
        {"repository_path": str(tmp_path), "test_logs": "FAILED a.py::test_x"}
    )
    prompt = fake.structured.messages[1].content
    return out, prompt


def test_fetch_sem_url_retorna_vazio(monkeypatch) -> None:
    monkeypatch.delenv("RAG_URL", raising=False)
    assert fetch_rag_context("qualquer coisa") == ""


def test_fetch_servidor_fora_retorna_vazio(monkeypatch) -> None:
    monkeypatch.setenv("RAG_URL", "http://127.0.0.1:1")
    assert fetch_rag_context("qualquer coisa") == ""


def test_analyst_inclui_rag_quando_ha(tmp_path, monkeypatch) -> None:
    out, prompt = _analyst_with_fake_llm(monkeypatch, tmp_path, "trecho similar: def f(): ...")
    assert out["target_files"] == ["a.py"]
    assert "CONTEXTO SEMÂNTICO ADICIONAL" in prompt
    assert "trecho similar" in prompt


def test_analyst_identico_sem_rag(tmp_path, monkeypatch) -> None:
    out, prompt = _analyst_with_fake_llm(monkeypatch, tmp_path, "")
    assert out["target_files"] == ["a.py"]
    assert "CONTEXTO SEMÂNTICO" not in prompt
