import os
import time
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
        # Identifica o ecossistema para rodar o comando correto
        if os.path.exists(os.path.join(repo_path, "package.json")):
            cmd = ["npm", "test"]
        elif os.path.exists(os.path.join(repo_path, "Makefile")):
            cmd = ["make", "test"]
        else:
            cmd = ["pytest"]
            
        result = subprocess.run(
            cmd,
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
    needs_research: bool = Field(default=False, description="True se o erro envolver HTTP 404, URLs ou APIs externas que precisam de consulta na web.")
    search_queries: List[str] = Field(default_factory=list, description="Lista de queries para pesquisar na web.")
    target_files: List[str] = Field(description="Lista de arquivos de código fonte que o programador deve modificar para corrigir o erro.")
    analysis: str = Field(description="Explicação técnica do bug e instruções claras para o programador de como corrigir.")

def analyst_node(state: AgentState) -> dict:
    """Analisa logs de erro para identificar causa raiz e arquivos afetados."""
    print("\n[Analyst] Analisando logs e o código-fonte do projeto...")
    
    repo_path = state.get("repository_path", ".")
    
    # Lê arquivos de código do diretório para dar contexto, ignorando pastas pesadas
    code_context = ""
    allowed_extensions = {".py", ".js", ".ts", ".c", ".cpp", ".h", ".java", ".go"}
    ignored_dirs = {".git", "__pycache__", "node_modules", "venv", ".venv", "env", "build", "dist"}
    
    for root, dirs, files in os.walk(repo_path):
        # Modifica a lista dirs in-place para que o os.walk não entre nas pastas ignoradas
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        
        for file in files:
            if any(file.endswith(ext) for ext in allowed_extensions):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        code_context += f"\n--- Arquivo: {file} ---\n{f.read()}\n"
                except Exception as e:
                    code_context += f"\n--- Arquivo: {file} (Erro ao ler: {e}) ---\n"
    
    # Inicializa o LLM
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, max_retries=5)
    structured_llm = llm.with_structured_output(AnalystOutput)
    
    sys_msg = SystemMessage(content=(
        "Você é um Engenheiro DevOps/QA Sênior. Sua tarefa é analisar logs de teste do Pytest.\n"
        "Identifique a causa raiz da falha.\n"
        "Use o contexto do código-fonte fornecido para encontrar com exatidão onde o bug está.\n"
        "Indique os arquivos que precisam ser alterados e explique a correção detalhadamente.\n"
        "Se a correção exigir alterações em múltiplos arquivos ao mesmo tempo, inclua TODOS ELES na sua lista de arquivos alvo.\n"
        "MUITO IMPORTANTE: Se o erro envolver HTTP 404, URLs ou APIs externas, defina needs_research=True para validar a URL correta na web.\n"
        "Se for um erro de sistema (ex: falta de dependência, banco offline), marque is_fatal=True."
    ))
    
    human_msg = HumanMessage(content=f"Logs do teste:\n{state.get('test_logs', '')}\n\nCódigo-fonte atual do projeto:\n{code_context}")
    
    result = structured_llm.invoke([sys_msg, human_msg])
    
    if result.is_fatal:
        return {"status": "fatal", "changes_history": [{"analyst_instruction": result.analysis}]}
        
    return {
        "target_files": result.target_files,
        "needs_research": result.needs_research,
        "search_queries": result.search_queries,
        "changes_history": [{"analyst_instruction": result.analysis}]
    }

class FileUpdate(BaseModel):
    file_name: str = Field(description="Nome do arquivo que está sendo corrigido.")
    updated_code: str = Field(description="O código-fonte completo e corrigido.")

def research_node(state: AgentState) -> dict:
    """Faz buscas na internet para encontrar documentação oficial."""
    print("\n[Research] Realizando pesquisa na web para validar APIs/documentação...")
    queries = state.get("search_queries", [])
    
    try:
        from langchain_community.tools import DuckDuckGoSearchRun
        search = DuckDuckGoSearchRun()
    except ImportError:
        return {"research_data": "ERRO: Instale a biblioteca executando: pip install duckduckgo-search langchain_community"}
        
    research_results = ""
    for q in queries:
        print(f"  -> Pesquisando: {q}")
        try:
            res = search.invoke(q)
            research_results += f"Resultados para '{q}':\n{res}\n\n"
        except Exception as e:
            research_results += f"Falha ao pesquisar '{q}': {e}\n\n"
            
    return {"research_data": research_results, "needs_research": False}

class ProgrammerOutput(BaseModel):
    file_updates: List[FileUpdate] = Field(description="Lista de arquivos com seus respectivos códigos atualizados.")

def programmer_node(state: AgentState) -> dict:
    print("\n[Programmer] Escrevendo a correção no código...")
    
    repo_path = state.get("repository_path", ".")
    target_files = state.get("target_files", [])
    history = state.get("changes_history", [])
    analyst_instruction = history[-1].get("analyst_instruction", "") if history else ""
    
    if not target_files:
        return {"changes_history": [{"programmer_action": "Nenhum arquivo alvo definido pelo analista."}]}
        
    # Lê TODOS os arquivos alvos definidos pelo Analista
    current_codes = ""
    for file in target_files:
        file_path = os.path.join(repo_path, file)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                current_codes += f"\n--- {file} ---\n{f.read()}\n"
        except Exception as e:
            return {"changes_history": [{"programmer_action": f"Erro ao ler {file}: {e}"}]}
        
    # Gera o código corrigido via LLM
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, max_retries=5)
    structured_llm = llm.with_structured_output(ProgrammerOutput)
    
    sys_msg = SystemMessage(content=(
        "Você é um Engenheiro de Software Especialista. Reescreva os códigos fornecidos para corrigir os bugs apontados na instrução.\n"
        "Se a instrução pedir para alterar múltiplos arquivos, garanta que você retornou o código atualizado e completo para CADA UM dos arquivos afetados."
    ))
    
    human_msg_content = f"Códigos atuais:\n{current_codes}\n\nInstrução do Analista:\n{analyst_instruction}"
    research_data = state.get("research_data", "")
    if research_data:
        human_msg_content += f"\n\nContexto extraído da Web (Use essas informações para corrigir as URLs/APIs):\n{research_data}"
        
    human_msg = HumanMessage(content=human_msg_content)
    
    result = structured_llm.invoke([sys_msg, human_msg])
    
    # Human-in-the-loop: Aprovação antes de salvar
    print("\n[Aprovação Necessária] Códigos sugeridos:\n")
    for update in result.file_updates:
        print(f"--- {update.file_name} ---")
        print(update.updated_code)
    print("-" * 50)
    
    # Verifica se está rodando em ambiente CI/CD (GitHub Actions, etc)
    is_ci = os.getenv("CI") == "true"
    
    if not is_ci:
        aprovacao = input("Aprovar estas alterações? (Y/N): ").strip().upper()
        if aprovacao != 'Y':
            print("Alteração rejeitada pelo usuário.")
            return {"status": "fatal", "changes_history": [{"programmer_action": "Alteração rejeitada pelo usuário humano."}]}
    else:
        print("🤖 Modo CI detectado! Pulando aprovação humana e aplicando correções automaticamente...")

    # Sobrescreve os arquivos com a correção
    for update in result.file_updates:
        file_path = os.path.join(repo_path, update.file_name)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(update.updated_code)
        print(f"Arquivo {update.file_name} atualizado com sucesso.")
        
    nomes_arquivos = ", ".join([u.file_name for u in result.file_updates])
    return {"changes_history": [{"programmer_action": f"Arquivos corrigidos: {nomes_arquivos}"}]}

def report_node(state: AgentState) -> dict:
    print("\n[Report] Gerando relatório final da execução...")
    
    # Pausa de segurança para evitar erro 429 (Rate Limit) na API gratuita do Gemini
    print("[Report] Aguardando alguns segundos para respeitar o limite da API...")
    time.sleep(10)
    
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, max_retries=5)
    
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

def route_after_analyst(state: AgentState) -> str:
    """Define se vai direto pro programador ou se pesquisa na web antes."""
    if state.get("status") == "fatal":
        return "generate_report"
    if state.get("needs_research", False):
        return "research"
    return "programmer"

def build_self_healer_graph() -> StateGraph:
    """Constrói e compila o grafo do agente."""
    workflow = StateGraph(AgentState)

    # Nós
    workflow.add_node("run_tests", run_tests_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("research", research_node)
    workflow.add_node("programmer", programmer_node)
    workflow.add_node("generate_report", report_node)
    workflow.add_node("git_commit", git_commit_node)

    # Arestas
    workflow.add_edge(START, "run_tests")
    workflow.add_conditional_edges("run_tests", route_test_results)
    
    # Roteamento Inteligente (RAG / Web Search)
    workflow.add_conditional_edges("analyst", route_after_analyst)
    workflow.add_edge("research", "programmer")
    
    workflow.add_edge("programmer", "run_tests")
    workflow.add_edge("generate_report", "git_commit")
    workflow.add_edge("git_commit", END)

    # Compilação
    app = workflow.compile()
    return app