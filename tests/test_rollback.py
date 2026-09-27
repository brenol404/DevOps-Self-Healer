"""Teste do rollback — git real em diretório temporário, sem LLM."""

import subprocess
from pathlib import Path

from agent.graph import auto_rollback_node


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "codigo.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=path, check=True)


def test_rollback_restaura_arquivos_sujos(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "codigo.py").write_text("x = QUEBRADO!!!\n", encoding="utf-8")
    (tmp_path / "lixo_novo.py").write_text("novo\n", encoding="utf-8")

    out = auto_rollback_node({"repository_path": str(tmp_path)})

    assert (tmp_path / "codigo.py").read_text(encoding="utf-8") == "x = 1\n"
    assert not (tmp_path / "lixo_novo.py").exists()  # clean -fd remove untracked
    assert "reset --hard" in str(out["changes_history"])


def test_rollback_fora_de_repo_registra_falha_sem_levantar(tmp_path: Path) -> None:
    out = auto_rollback_node({"repository_path": str(tmp_path / "nao-repo")})
    assert "Falha no rollback" in str(out["changes_history"])
