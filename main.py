"""DevOps Self-Healer: roda testes, diagnostica falhas, corrige e commita.

Uso:
    python main.py --repo ./meu-projeto --max-attempts 5
    python main.py --repo ./meu-projeto --ci   # sem aprovação humana (automação)
"""

from __future__ import annotations

import argparse
import os
from pprint import pprint

from dotenv import load_dotenv

from agent.graph import build_self_healer_graph


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        default="projeto_cobaia",
        help="diretório do projeto-alvo (default: projeto_cobaia, via setup_cobaia.py)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="tentativas de correção antes do rollback (default: 3)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="pula a aprovação humana (equivale a CI=true; sem rede de segurança)",
    )
    args = parser.parse_args()

    # Carrega variáveis de ambiente
    load_dotenv()
    if args.ci:
        os.environ["CI"] = "true"

    print("Inicializando o DevOps-Self-Healer...")

    # Compila o grafo
    app = build_self_healer_graph()

    # Define o estado inicial
    initial_state = {
        "repository_path": args.repo,
        "max_attempts": args.max_attempts,
        "current_attempt": 0,
        "status": "pending",
    }

    print(f"Alvo definido: {initial_state['repository_path']}\nIniciando o loop de testes...\n")

    # Executa o fluxo
    final_state = app.invoke(initial_state)

    print("\nExecução finalizada!")
    if "final_report" in final_state:
        print("\n=== RELATÓRIO DO AGENTE ===")
        print(final_state["final_report"])
        print("===========================\n")

        # Exporta o relatório para um arquivo .md
        with open("relatorio_execucao.md", "w", encoding="utf-8") as f:
            f.write(final_state["final_report"])
        print("📄 Relatório exportado com sucesso para 'relatorio_execucao.md'!")
    else:
        pprint({k: v for k, v in final_state.items() if k != "test_logs"})


if __name__ == "__main__":
    main()
