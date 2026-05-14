import os
import subprocess
from langgraph.graph import StateGraph, START, END
from agent.state import AgentState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from typing import List

def run_tests_node(state: AgentState) -> dict:
    """Executa os testes via pytest e atualiza o estado."""
    # Se o status for fatal (ex: usuário cancelou a correção), não tenta rodar o teste
    if state.get("status") == "fatal":
        return {}
        
    repo_path = state.get("repository_path", ".")
    current_attempt = state.get("current_attempt", 0) + 1
    
    try:
        # Executa pytest
        result = subprocess.run(
            ["pytest"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False
        )
        
        # Captura logs de saída
        logs = result.stdout
        if result.stderr:
            logs += f"\n{result.stderr}"
            
        status = "passed" if result.returncode == 0 else "failed"
        
        return {"current_attempt": current_attempt, "test_logs": logs, "status": status}
        
    except Exception as e:
        # Falha crítica de execução
        return {"current_attempt": current_attempt, "test_logs": str(e), "status": "fatal"}

class AnalystOutput(BaseModel):
    is_fatal: bool = Field(description="True se o erro for puramente de infraestrutura/ambiente e não puder ser corrigido alterando os scripts da pasta.")
    target_files: List[str] = Field(description="Lista de arquivos de código fonte que o programador deve modificar para corrigir o erro.")
    analysis: str = Field(description="Explicação técnica do bug e instruções claras para o programador de como corrigir.")

def analyst_node(state: AgentState) -> dict:
    """Analisa logs de erro para identificar causa raiz e arquivos afetados."""
    print("\n[Analyst] Analisando logs e o código-fonte do projeto...")
    
    repo_path = state.get("repository_path", ".")
    
    # Lê todos os arquivos .py do diretório para dar contexto ao LLM
    code_context = ""
    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        code_context += f"\n--- Arquivo: {file} ---\n{f.read()}\n"
                except Exception as e:
                    code_context += f"\n--- Arquivo: {file} (Erro ao ler: {e}) ---\n"
    
    # Inicializa o LLM
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(AnalystOutput)
    
    sys_msg = SystemMessage(content=(
        "Você é um Engenheiro DevOps/QA Sênior. Sua tarefa é analisar logs de teste do Pytest.\n"
        "Identifique a causa raiz da falha.\n"
        "Use o contexto do código-fonte fornecido para encontrar com exatidão onde o bug está.\n"
        "Indique os arquivos que precisam ser alterados e explique a correção detalhadamente.\n"
        "Se for um erro de sistema (ex: falta de dependência, banco offline), marque is_fatal=True."
    ))
    
    human_msg = HumanMessage(content=f"Logs do teste:\n{state.get('test_logs', '')}\n\nCódigo-fonte atual do projeto:\n{code_context}")
    
    result = structured_llm.invoke([sys_msg, human_msg])
    
    if result.is_fatal:
        return {"status": "fatal", "changes_history": [{"analyst_instruction": result.analysis}]}
        
    return {
        "target_files": result.target_files,
        "changes_history": [{"analyst_instruction": result.analysis}]
    }

class ProgrammerOutput(BaseModel):
    updated_code: str = Field(description="O código-fonte completo e corrigido, pronto para ser salvo. Retorne apenas código válido.")

def programmer_node(state: AgentState) -> dict:
    print("\n[Programmer] Escrevendo a correção no código...")
    
    repo_path = state.get("repository_path", ".")
    target_files = state.get("target_files", [])
    history = state.get("changes_history", [])
    analyst_instruction = history[-1].get("analyst_instruction", "") if history else ""
    
    if not target_files:
        return {"changes_history": [{"programmer_action": "Nenhum arquivo alvo definido pelo analista."}]}
        
    # Foca no primeiro arquivo alvo
    target_file = target_files[0]
    file_path = os.path.join(repo_path, target_file)
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            current_code = f.read()
    except Exception as e:
        return {"changes_history": [{"programmer_action": f"Erro ao ler {target_file}: {e}"}]}
        
    # Gera o código corrigido via LLM
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    structured_llm = llm.with_structured_output(ProgrammerOutput)
    
    sys_msg = SystemMessage(content=(
        "Você é um Engenheiro de Software Especialista. Reescreva o código fornecido para corrigir os bugs apontados na instrução."
    ))
    human_msg = HumanMessage(content=f"Código atual:\n{current_code}\n\nInstrução:\n{analyst_instruction}")
    
    result = structured_llm.invoke([sys_msg, human_msg])
    
    # Human-in-the-loop: Aprovação antes de salvar
    print(f"\n[Aprovação Necessária] Código sugerido para {target_file}:\n")
    print(result.updated_code)
    print("-" * 50)
    
    aprovacao = input("Aprovar esta alteração? (Y/N): ").strip().upper()
    if aprovacao != 'Y':
        print("Alteração rejeitada pelo usuário.")
        return {"status": "fatal", "changes_history": [{"programmer_action": "Alteração rejeitada pelo usuário humano."}]}
    
    # Sobrescreve o arquivo com a correção
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(result.updated_code)
        
    print(f"Arquivo {target_file} atualizado com sucesso.")
    return {"changes_history": [{"programmer_action": f"Arquivo {target_file} corrigido."}]}

def report_node(state: AgentState) -> dict:
    print("\n[Report] Gerando relatório final da execução...")
    
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    
    sys_msg = SystemMessage(content=(
        "Você é um assistente de DevOps. Gere um relatório Markdown executivo, "
        "minimalista e sem emojis resumindo o resultado da execução do agente de auto-cura."
    ))
    
    human_msg = HumanMessage(content=f"""
    Status Final: {state.get('status')}
    Tentativas Usadas: {state.get('current_attempt')} / {state.get('max_attempts')}
    Histórico de Ações: {state.get('changes_history')}
    """)
    
    response = llm.invoke([sys_msg, human_msg])
    return {"final_report": response.content}

def git_commit_node(state: AgentState) -> dict:
    """Realiza o commit das alterações automaticamente se o teste passou."""
    if state.get("status") != "passed":
        return {} # Não faz commit se falhou ou foi abortado
        
    print("\n[Git] Realizando commit automático das correções...")
    repo_path = state.get("repository_path", ".")
    
    try:
        # Adiciona os arquivos modificados
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
        
        # Faz o commit com uma mensagem explicativa
        commit_msg = "fix: Correção automática aplicada pelo Agente DevOps-Self-Healer"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_path, capture_output=True, check=True)
        
        print("[Git] Commit realizado com sucesso!")
        return {"changes_history": [{"git_action": "Commit realizado com sucesso."}]}
    except Exception as e:
        print(f"[Git] Aviso: Falha ao realizar o commit. Erro: {e}")
        return {"changes_history": [{"git_action": f"Falha no commit: {e}"}]}

def route_test_results(state: AgentState) -> str:
    """Define o próximo nó baseado no status dos testes."""
    if state.get("status") == "passed":
        return "generate_report"
    
    if state.get("status") == "fatal":
        return "generate_report"
    
    if state.get("current_attempt", 0) >= state.get("max_attempts", 3):
        return "generate_report"
    
    # Tenta novamente se limite não foi atingido
    return "analyst"

def build_self_healer_graph() -> StateGraph:
    """Constrói e compila o grafo do agente."""
    workflow = StateGraph(AgentState)

    # Nós
    workflow.add_node("run_tests", run_tests_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("programmer", programmer_node)
    workflow.add_node("generate_report", report_node)
    workflow.add_node("git_commit", git_commit_node)

    # Arestas
    workflow.add_edge(START, "run_tests")
    workflow.add_conditional_edges("run_tests", route_test_results)
    workflow.add_edge("analyst", "programmer")
    workflow.add_edge("programmer", "run_tests")
    workflow.add_edge("generate_report", "git_commit")
    workflow.add_edge("git_commit", END)

    # Compilação
    app = workflow.compile()
    return app