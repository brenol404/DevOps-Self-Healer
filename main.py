from agent.graph import build_self_healer_graph
from pprint import pprint
from dotenv import load_dotenv

def main():
    # Carrega variáveis de ambiente
    load_dotenv()
    
    print("Inicializando o DevOps-Self-Healer...")
    
    # Compila o grafo
    app = build_self_healer_graph()
    
    # Define o estado inicial
    initial_state = {
        "repository_path": "projeto_cobaia",
        "max_attempts": 3,
        "current_attempt": 0,
        "status": "pending"
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

if __name__ == "__main__":
    main()