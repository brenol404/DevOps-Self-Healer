"""Segurança de escrita: nomes vindos do LLM não escapam do repo."""

import os

import pytest

from agent.graph import apply_fixes_node, qa_engineer_node, safe_join


def test_safe_join_aceita_relativo_contido(tmp_path) -> None:
    out = safe_join(str(tmp_path), "pkg/modulo.py")
    assert out == str(tmp_path / "pkg" / "modulo.py")


def test_safe_join_rejeita_fuga(tmp_path) -> None:
    for evil in ("../evil.py", "../../x.py", "/tmp/evil.py", "", ".", "a/../../b.py"):
        with pytest.raises(ValueError, match="inválido|fora do repositório"):
            safe_join(str(tmp_path), evil)


def test_apply_rejeita_tudo_sem_escrever_nada(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    legit = tmp_path / "ok.py"
    legit.write_text("original\n", encoding="utf-8")
    state = {
        "repository_path": str(tmp_path),
        "proposed_updates": [
            {"file_name": "ok.py", "updated_code": "novo\n"},
            {"file_name": "../evil.py", "updated_code": "pwned\n"},
        ],
    }
    out = apply_fixes_node(state)
    assert out["status"] == "fatal"
    assert "segurança" in str(out["changes_history"])
    assert legit.read_text(encoding="utf-8") == "original\n"  # nada foi escrito


def test_apply_sem_chaves_vira_fatal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    out = apply_fixes_node({"repository_path": str(tmp_path), "proposed_updates": [{}]})
    assert out["status"] == "fatal"


def test_qa_rejeita_nome_malicioso(tmp_path, monkeypatch) -> None:
    import agent.graph as G

    class _FakeStructured:
        def invoke(self, messages):
            class _R:
                test_name = "../../evil_test.py"
                test_code = "def test_x(): pass\n"

            return _R()

    class _FakeLLM:
        def with_structured_output(self, cls):
            return _FakeStructured()

    monkeypatch.setattr(G, "get_llm", lambda *a, **k: _FakeLLM())
    out = qa_engineer_node({"repository_path": str(tmp_path), "changes_history": []})
    assert out["status"] == "fatal"
    assert not os.path.exists("/tmp/evil_test.py")
    assert not list(tmp_path.iterdir())
