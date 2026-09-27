import os
import time
import re
import json
import urllib.request
import subprocess
from langgraph.graph import StateGraph, START, END
from agent.state import AgentState
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from typing import List


def safe_join(repo_path: str, file_name: str) -> str:
    """Junta caminho confinado ao repositório; rejeita fuga (fail-closed).

    Nomes vêm do LLM: `../evil.py` ou `/tmp/evil.py` escapariam do projeto
    via `os.path.join`. Aqui só passam relativos contidos no repo.
    """
    from pathlib import Path

    if not file_name or not isinstance(file_name, str):
        raise ValueError(f"nome de arquivo inválido: {file_name!r}")
    base = Path(repo_path).resolve()
    target = (base / file_name).resolve()
    if target == base or base not in target.parents:
        raise ValueError(f"nome de arquivo fora do repositório: {file_name!r}")
    return str(target)


def safe_invoke(llm_instance, messages, max_retries=3):
    """Invoca o LLM com tratamento automático e reativo para Rate Limits (Erro 429)."""
    tentativas = 0
    while tentativas < max_retries:
        try:
            return llm_instance.invoke(messages)
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                tentativas += 1
                espera = 60 * tentativas
                print(f"\n⏳ [Rate Limit] A API do Google bloqueou por excesso de uso (Tentativa {tentativas}/{max_retries}).")
                print(f"🤖 Pausando por {espera} segundos para tentar novamente...")
                time.sleep(espera)
            else:
                raise e
    
    print("\n❌ [Erro Fatal] O limite de cota da API foi atingido repetidamente. Abortando execução.")
    raise RuntimeError("Cota da API esgotada. Tente novamente amanhã ou utilize outra chave de API.")

def get_llm(temperature=0, max_retries=5):
    """Fábrica de instâncias de LLM (Multi-Modelo) baseada no .env"""
    provider = os.getenv("LLM_PROVIDER", "google").lower()
    model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model_name, temperature=temperature, max_retries=max_retries)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model_name, temperature=temperature, max_retries=max_retries)
    elif provider == "ollama":
        from langchain_community.chat_models import ChatOllama
        return ChatOllama(model=model_name, temperature=temperature)
    else:
        raise ValueError(f"Provedor LLM não suportado no .env: {provider}")

def run_tests_node(state: AgentState) -> dict:
    """Executa os testes via pytest e atualiza o estado."""
    # Se o status for fatal (ex: usuário cancelou a correção), não tenta rodar o teste
    if state.get("status") == "fatal":
        return {}
        
    print("\n[Pytest] Executando suíte de testes...")
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
        
        # Reseta o contador de revisões para a nova tentativa de correção
        return {"current_attempt": current_attempt, "test_logs": logs, "status": status, "review_attempts": 0}
        
    except Exception as e:
        # Falha crítica de execução
        return {"current_attempt": current_attempt, "test_logs": str(e), "status": "fatal", "review_attempts": 0}

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
    
    # 1. Gera um Mapa do Repositório (apenas estrutura de pastas/arquivos)
    repo_map = "Estrutura do Repositório:\n"
    all_files = []
    allowed_extensions = {".py", ".js", ".ts", ".c", ".cpp", ".h", ".java", ".go"}
    ignored_dirs = {".git", "__pycache__", "node_modules", "venv", ".venv", "env", "build", "dist"}
    
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for file in files:
            if any(file.endswith(ext) for ext in allowed_extensions):
                # Guarda o caminho relativo do arquivo
                rel_path = os.path.relpath(os.path.join(root, file), repo_path)
                repo_map += f"- {rel_path}\n"
                all_files.append(rel_path)
                
    # 2. Busca Inteligente de Contexto (Traceback Parser)
    test_logs = state.get('test_logs', '')
    mentioned_files = set()
    
    # Procura quais arquivos do mapa foram mencionados nos logs de erro
    for f in all_files:
        file_basename = os.path.basename(f)
        if file_basename in test_logs:
            mentioned_files.add(f)
            
    # 3. Lê apenas o conteúdo dos arquivos relevantes para não estourar tokens
    code_context = f"{repo_map}\n\nCONTEÚDO DOS ARQUIVOS RELEVANTES (Envolvidos no Crash/Log):\n"
    
    if not mentioned_files:
        code_context += "[Aviso: Nenhum arquivo específico foi detectado no log de erro. O projeto pode estar sem arquivos ou o log não apontou a origem.]\n"
        
    for f in mentioned_files:
        file_path = os.path.join(repo_path, f)
        try:
            # Code RAG: Extrai apenas o contexto afetado usando Regex no Traceback
            file_basename = os.path.basename(f)
            # Captura menções do tipo 'file.py", line 42' ou 'file.js:42'
            pattern = re.compile(re.escape(file_basename) + r'["\',:]*\s*(?:line)?\s*[:]*\s*(\d+)', re.IGNORECASE)
            matches = pattern.findall(test_logs)
            
            with open(file_path, "r", encoding="utf-8") as file_obj:
                lines = file_obj.readlines()
                
            if not matches:
                # Se não encontrou linha específica, limita a 300 linhas por segurança
                content = "".join(lines[:300])
                if len(lines) > 300:
                    content += f"\n... [{len(lines) - 300} linhas omitidas para economizar tokens] ...\n"
            else:
                # Extrai uma "janela" de código (25 linhas antes e depois do erro)
                line_numbers = sorted(list(set(int(m) for m in matches)))
                extracted_blocks = []
                last_end = 0
                context_window = 25
                
                for line_num in line_numbers:
                    start = max(0, line_num - context_window - 1)
                    end = min(len(lines), line_num + context_window)
                    
                    if start < last_end:
                        start = last_end # Previne duplicar blocos sobrepostos
                        
                    if start < end:
                        if start > last_end:
                            extracted_blocks.append(f"\n... (Código omitido... Pulando para linha {start+1}) ...\n")
                        extracted_blocks.append("".join(lines[start:end]))
                        last_end = end
                        
                content = "".join(extracted_blocks)

            code_context += f"\n--- Arquivo: {f} ---\n{content}\n"
        except Exception as e:
            code_context += f"\n--- Arquivo: {f} (Erro ao ler: {e}) ---\n"
    
    # Inicializa o LLM
    llm = get_llm()
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
    
    result = safe_invoke(structured_llm, [sys_msg, human_msg])
    
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
    reviewer_feedback = state.get("reviewer_feedback", "")
    
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
    llm = get_llm()
    structured_llm = llm.with_structured_output(ProgrammerOutput)
    
    sys_msg = SystemMessage(content=(
        "Você é um Engenheiro de Software Especialista. Reescreva os códigos fornecidos para corrigir os bugs apontados na instrução.\n"
        "Se a instrução pedir para alterar múltiplos arquivos, garanta que você retornou o código atualizado e completo para CADA UM dos arquivos afetados."
    ))
    
    human_msg_content = f"Códigos atuais:\n{current_codes}\n\nInstrução do Analista:\n{analyst_instruction}"
    research_data = state.get("research_data", "")
    if research_data:
        human_msg_content += f"\n\nContexto extraído da Web (Use essas informações para corrigir as URLs/APIs):\n{research_data}"
        
    if reviewer_feedback:
        human_msg_content += f"\n\n[ATENÇÃO] Feedback do Code Reviewer na tentativa anterior:\n{reviewer_feedback}\nPor favor, ajuste seu código para atender a esta revisão estritamente."
        
    human_msg = HumanMessage(content=human_msg_content)
    
    result = safe_invoke(structured_llm, [sys_msg, human_msg])
    
    # Prepara as propostas em memória (NÃO salva no disco ainda)
    updates = [{"file_name": u.file_name, "updated_code": u.updated_code} for u in result.file_updates]
    nomes_arquivos = ", ".join([u["file_name"] for u in updates])
    
    return {
        "proposed_updates": updates,
        "changes_history": [{"programmer_action": f"Código gerado para: {nomes_arquivos}"}]
    }

class ReviewerOutput(BaseModel):
    is_approved: bool = Field(description="True se o código segue princípios de Clean Code/SOLID e resolve o problema sem más práticas.")
    feedback: str = Field(description="Comentário explicando o que precisa melhorar (se rejeitado) ou justificativa de aprovação.")

def reviewer_node(state: AgentState) -> dict:
    print("\n[Reviewer] Analisando a qualidade do código gerado (SOLID / Clean Code)...")
    updates = state.get("proposed_updates", [])
    review_attempts = state.get("review_attempts", 0) + 1
    
    if not updates:
        return {"review_approved": False, "reviewer_feedback": "Nenhuma alteração proposta para revisar.", "review_attempts": review_attempts}
        
    code_to_review = ""
    for u in updates:
        code_to_review += f"\n--- {u['file_name']} ---\n{u['updated_code']}\n"
        
    llm = get_llm()
    structured_llm = llm.with_structured_output(ReviewerOutput)
    
    sys_msg = SystemMessage(content=(
        "Você é um Revisor de Código Sênior (Code Reviewer).\n"
        "Sua tarefa é avaliar o código gerado pelo programador.\n"
        "Verifique se o código resolve o problema sem introduzir gambiarras, complexidade desnecessária ou variáveis não utilizadas.\n"
        "Se estiver limpo e conciso, aprove (is_approved=True). Se estiver ruim, rejeite (is_approved=False) e instrua como reescrever."
    ))
    human_msg = HumanMessage(content=f"Código a ser revisado:\n{code_to_review}")
    
    result = safe_invoke(structured_llm, [sys_msg, human_msg])
    status_msg = "Aprovado" if result.is_approved else "Rejeitado"
    print(f"[Reviewer] Status: {status_msg} | Tentativa {review_attempts}/3 | Feedback: {result.feedback}")
    
    # Aborta o ciclo se o código for rejeitado muitas vezes (Proteção contra Loop Infinito)
    if not result.is_approved and review_attempts >= 3:
        print("[Reviewer] ❌ Limite de revisões atingido! O programador não conseguiu aprovação. Abortando a tentativa de correção...")
        return {
            "review_approved": False,
            "reviewer_feedback": result.feedback,
            "review_attempts": review_attempts,
            "status": "fatal",
            "changes_history": [{"reviewer_action": f"Revisão falhou após 3 tentativas. Feedback final: {result.feedback}"}]
        }
    
    return {
        "review_approved": result.is_approved,
        "reviewer_feedback": result.feedback,
        "review_attempts": review_attempts,
        "changes_history": [{"reviewer_action": f"Revisão {status_msg} (Tentativa {review_attempts}): {result.feedback}"}]
    }

def apply_fixes_node(state: AgentState) -> dict:
    print("\n[Apply Fixes] Solicitando aprovação final para salvar no disco...")
    repo_path = state.get("repository_path", ".")
    updates = state.get("proposed_updates", [])
    
    if not updates:
        return {"status": "fatal", "changes_history": [{"apply_action": "Erro: Nenhuma alteração para aplicar."}]}
        
    # Human-in-the-loop: Aprovação antes de salvar
    print("\n[Aprovação Necessária] Códigos sugeridos pelo Programador e APROVADOS pelo Reviewer:\n")
    for update in updates:
        print(f"--- {update.get('file_name', '?')} ---")
        print(update.get("updated_code", ""))
    print("-" * 50)
    
    is_ci = os.getenv("CI") == "true"
    
    if not is_ci:
        aprovacao = input("Aprovar e aplicar estas alterações no projeto? (Y/N): ").strip().upper()
        if aprovacao != 'Y':
            print("Alteração rejeitada pelo usuário.")
            return {"status": "fatal", "changes_history": [{"apply_action": "Alteração rejeitada pelo usuário humano."}]}
    else:
        print("🤖 Modo CI detectado! Pulando aprovação humana e aplicando correções no disco...")

    # Valida TODAS as propostas antes de escrever qualquer uma (fail-closed:
    # nomes vêm do LLM e update sem chave não deve derrubar com KeyError).
    planned: list[tuple[str, str, str]] = []
    try:
        for update in updates:
            name = update.get("file_name", "")
            code = update.get("updated_code", "")
            if not isinstance(code, str) or not code:
                raise ValueError(f"conteúdo vazio para {name!r}")
            planned.append((name, safe_join(repo_path, name), code))
    except (ValueError, AttributeError) as exc:
        return {
            "status": "fatal",
            "changes_history": [{"apply_action": f"Proposta rejeitada (segurança): {exc}"}],
        }

    # Sobrescreve os arquivos com a correção real
    for name, file_path, code in planned:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"Arquivo {name} salvo no disco com sucesso.")
        
    nomes_arquivos = ", ".join([u["file_name"] for u in updates])
    # Limpa as propostas em memória pois já foram aplicadas
    return {"changes_history": [{"apply_action": f"Arquivos salvos no disco: {nomes_arquivos}"}], "proposed_updates": [], "reviewer_feedback": ""}

class QAOutput(BaseModel):
    test_code: str = Field(description="Código fonte completo do novo arquivo de testes usando pytest.")
    test_name: str = Field(description="Nome do arquivo Python, começando obrigatoriamente com 'test_' (ex: test_regression_auto.py).")

def qa_engineer_node(state: AgentState) -> dict:
    print("\n[QA Engineer] Criando testes proativos de regressão para blindar as alterações...")
    
    repo_path = state.get("repository_path", ".")
    history = state.get("changes_history", [])
    
    # Pega o que foi alterado neste ciclo
    updates_str = str([h for h in history if "apply_action" in h or "programmer_action" in h])
    
    llm = get_llm()
    structured_llm = llm.with_structured_output(QAOutput)
    
    sys_msg = SystemMessage(content=(
        "Você é um Engenheiro de QA de Software Especialista. Um desenvolvedor acabou de corrigir bugs no sistema.\n"
        "Sua tarefa é criar um novo arquivo de testes unitários ou de integração (usando pytest) focado estritamente em garantir que as funções recém consertadas não voltem a quebrar.\n"
        "Importe os módulos corretamente considerando que seu arquivo estará na raiz do projeto. Retorne o código completo."
    ))
    
    human_msg = HumanMessage(content=f"Histórico das correções recentes que você deve blindar com testes:\n{updates_str}")
    
    result = safe_invoke(structured_llm, [sys_msg, human_msg])
    
    # Blindagem: Garante que não vamos sobrescrever um arquivo de teste existente
    test_file_name = result.test_name
    try:
        file_path = safe_join(repo_path, test_file_name)
    except ValueError as exc:
        return {
            "status": "fatal",
            "changes_history": [{"qa_action": f"Nome de teste rejeitado (segurança): {exc}"}],
        }
    
    counter = 1
    while os.path.exists(file_path):
        test_file_name = result.test_name.replace(".py", f"_auto_{counter}.py")
        file_path = os.path.join(repo_path, test_file_name)
        counter += 1

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(result.test_code)
        
    print(f"[QA Engineer] Novo teste salvo no disco: {test_file_name}")
    
    return {
        "proactive_tests_generated": True,
        "current_attempt": 0,
        "changes_history": [{"qa_action": f"Criado teste proativo: {result.test_name}"}]
    }

def report_node(state: AgentState) -> dict:
    print("\n[Report] Gerando relatório final da execução...")
    
    llm = get_llm()
    
    sys_msg = SystemMessage(content=(
        "Você é um assistente de DevOps. Gere um relatório Markdown executivo, "
        "minimalista e sem emojis resumindo o resultado da execução do agente de auto-cura."
    ))
    
    human_msg = HumanMessage(content=f"""
    Status Final: {state.get('status')}
    Tentativas Usadas: {state.get('current_attempt')} / {state.get('max_attempts')}
    Histórico de Ações: {state.get('changes_history')}
    """)
    
    response = safe_invoke(llm, [sys_msg, human_msg])
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

def auto_rollback_node(state: AgentState) -> dict:
    """Reverte o projeto para o estado original caso não consiga consertar o bug."""
    print("\n[Rollback] Falha crítica ou limite de tentativas atingido. Revertendo alterações (Git Reset)...")
    repo_path = state.get("repository_path", ".")
    
    try:
        subprocess.run(["git", "reset", "--hard"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(["git", "clean", "-fd"], cwd=repo_path, capture_output=True, check=True)
        print("[Rollback] Projeto restaurado ao estado original com sucesso.")
        return {"changes_history": [{"rollback_action": "Git reset --hard executado. Código revertido ao estado seguro."}]}
    except Exception as e:
        print(f"[Rollback] Erro ao tentar reverter o código: {e}")
        return {"changes_history": [{"rollback_action": f"Falha no rollback (Git): {e}"}]}

def notify_team_node(state: AgentState) -> dict:
    """Envia uma notificação via Webhook (Slack/Discord) informando o resultado."""
    print("\n[Webhook] Disparando notificação para a equipe...")
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        print("[Webhook] Nenhuma WEBHOOK_URL configurada no .env. Pulando notificação.")
        return {}
    
    status_emoji = "✅ Sucesso" if state.get("status") == "passed" else "❌ Falha/Abortado"
    payload = {
        "content": f"🤖 **DevOps-Self-Healer Executado!**\n\n**Projeto:** `{state.get('repository_path')}`\n**Status Final:** {status_emoji}\n**Tentativas:** {state.get('current_attempt')}/{state.get('max_attempts')}\n\nO sistema finalizou o ciclo de auto-cura."
    }
    try:
        req = urllib.request.Request(webhook_url, method="POST")
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, data=json.dumps(payload).encode('utf-8')) as response:
            print("[Webhook] Notificação enviada com sucesso!")
    except Exception as e:
        print(f"[Webhook] Erro ao enviar notificação: {e}")
        
    return {}

def route_test_results(state: AgentState) -> str:
    """Define o próximo nó baseado no status dos testes."""
    if state.get("status") == "passed":
        history_str = str(state.get("changes_history", []))
        # Se houve conserto de código e ainda não geramos testes proativos
        if "apply_action" in history_str and not state.get("proactive_tests_generated", False):
            return "qa_engineer"
        else:
            return "generate_report"
    
    if state.get("status") == "fatal":
        return "auto_rollback"
    
    if state.get("current_attempt", 0) >= state.get("max_attempts", 3):
        return "auto_rollback"
    
    # Tenta novamente se limite não foi atingido
    return "analyst"

def route_after_analyst(state: AgentState) -> str:
    """Define se vai direto pro programador ou se pesquisa na web antes."""
    if state.get("status") == "fatal":
        return "auto_rollback"
    if state.get("needs_research", False):
        return "research"
    return "programmer"

def route_after_reviewer(state: AgentState) -> str:
    """Decide se vai aplicar o código no disco ou voltar pro programador refazer."""
    if state.get("status") == "fatal":
        return "auto_rollback"
    if state.get("review_approved"):
        return "apply_fixes"
    return "programmer"

def route_after_apply(state: AgentState) -> str:
    """Se o usuário abortar a alteração, entra em rollback, se não, vai testar."""
    if state.get("status") == "fatal":
        return "auto_rollback"
    return "run_tests"

def build_self_healer_graph() -> StateGraph:
    """Constrói e compila o grafo do agente."""
    workflow = StateGraph(AgentState)

    # Nós
    workflow.add_node("run_tests", run_tests_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("research", research_node)
    workflow.add_node("programmer", programmer_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("apply_fixes", apply_fixes_node)
    workflow.add_node("qa_engineer", qa_engineer_node)
    workflow.add_node("generate_report", report_node)
    workflow.add_node("git_commit", git_commit_node)
    workflow.add_node("auto_rollback", auto_rollback_node)
    workflow.add_node("notify_team", notify_team_node)

    # Arestas
    workflow.add_edge(START, "run_tests")
    workflow.add_conditional_edges("run_tests", route_test_results)
    
    # Roteamento Inteligente (RAG / Web Search)
    workflow.add_conditional_edges("analyst", route_after_analyst)
    workflow.add_edge("research", "programmer")
    
    workflow.add_edge("programmer", "reviewer")
    workflow.add_conditional_edges("reviewer", route_after_reviewer)
    workflow.add_conditional_edges("apply_fixes", route_after_apply)
    
    workflow.add_edge("qa_engineer", "run_tests")
    workflow.add_edge("auto_rollback", "generate_report")
    workflow.add_edge("generate_report", "git_commit")
    workflow.add_edge("git_commit", "notify_team")
    workflow.add_edge("notify_team", END)

    # Compilação
    app = workflow.compile()
    return app