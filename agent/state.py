import operator
from typing import Annotated, TypedDict, List, Dict, Any

class AgentState(TypedDict):
    """Estado global do LangGraph."""
    repository_path: str
    
    # Logs do pytest
    test_logs: str
    
    # Arquivos para correção
    target_files: List[str]
    
    # Web Search / RAG
    needs_research: bool
    search_queries: List[str]
    research_data: str
    
    # Code Review e Aprovação
    proposed_updates: List[Dict[str, str]]
    reviewer_feedback: str
    review_approved: bool
    proactive_tests_generated: bool

    # Histórico de mudanças (append-only)
    changes_history: Annotated[List[Dict[str, Any]], operator.add]
    
    # Controle de tentativas
    current_attempt: int
    max_attempts: int
    review_attempts: int
    
    # Status: pending, passed, failed, fatal
    status: str
    
    # Relatório de execução
    final_report: str