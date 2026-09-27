"""Testes das funções de roteamento do grafo — puras, sem LLM."""

from agent.graph import (
    route_after_analyst,
    route_after_apply,
    route_after_reviewer,
    route_test_results,
)


def test_passed_sem_conserto_vai_para_relatorio() -> None:
    state = {"status": "passed", "changes_history": [], "proactive_tests_generated": False}
    assert route_test_results(state) == "generate_report"


def test_passed_com_conserto_vai_para_qa_uma_vez() -> None:
    state = {
        "status": "passed",
        "changes_history": [{"apply_action": "fix aplicado"}],
        "proactive_tests_generated": False,
    }
    assert route_test_results(state) == "qa_engineer"
    state["proactive_tests_generated"] = True
    assert route_test_results(state) == "generate_report"


def test_fatal_vai_para_rollback() -> None:
    for route in (route_test_results, route_after_analyst, route_after_reviewer, route_after_apply):
        assert route({"status": "fatal"}) == "auto_rollback"


def test_limite_de_tentativas_vai_para_rollback() -> None:
    assert route_test_results({"status": "failed", "current_attempt": 3, "max_attempts": 3}) == "auto_rollback"
    assert (
        route_test_results({"status": "failed", "current_attempt": 1, "max_attempts": 3})
        == "analyst"
    )


def test_analyst_com_pesquisa_vai_para_research() -> None:
    assert route_after_analyst({"status": "pending", "needs_research": True}) == "research"
    assert route_after_analyst({"status": "pending", "needs_research": False}) == "programmer"


def test_reviewer_aprovado_aplica_reprovado_refaz() -> None:
    assert route_after_reviewer({"status": "pending", "review_approved": True}) == "apply_fixes"
    assert route_after_reviewer({"status": "pending", "review_approved": False}) == "programmer"


def test_apply_sem_fatal_roda_testes() -> None:
    assert route_after_apply({"status": "passed"}) == "run_tests"
