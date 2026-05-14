import operator
from typing import Annotated, TypedDict, List, Dict, Any

class AgentState(TypedDict):
    """Estado global do LangGraph."""
    repository_path: str
    
    # Logs do pytest
    test_logs: str
    
    # Arquivos para correção
    target_files: List[str]
    
    # Histórico de mudanças (append-only)
    changes_history: Annotated[List[Dict[str, Any]], operator.add]
    
    # Controle de tentativas
    current_attempt: int
    max_attempts: int
    
    # Status: pending, passed, failed, fatal
    status: str
    
    # Relatório de execução
    final_report: str