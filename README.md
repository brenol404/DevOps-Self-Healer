# DevOps Self-Healer (Agentic AI)

Um agente autônomo baseado em Grafos de Estado (State Graphs) capaz de analisar falhas em testes de integração, ler o código-fonte, propor correções e realizar commits automaticamente utilizando Large Language Models (LLMs).

## Arquitetura e Stack Tecnológica
* **Orquestração de Agentes:** LangGraph
* **Inteligência Artificial:** Google Gemini 2.5 Flash via LangChain
* **Testes e Validação:** Pytest
* **Controle de Versão:** Git
* **Linguagem:** Python 3.12+

## Funcionalidades Atuais
* **Execução Cíclica de Testes:** Roda suítes de testes isoladas em repositórios alvo.
* **Injeção de Contexto (Context Retrieval):** Varre a base de código `.py` do projeto e fornece contexto completo para o LLM investigar a raiz do problema.
* **Geração de Código (Structured Output):** Utiliza Pydantic para forçar o LLM a retornar código Python limpo e pronto para produção, sem conversação desnecessária.
* **Aprovação Humana (Human-in-the-loop):** Interrompe o fluxo e exige autorização de um engenheiro antes de aplicar qualquer alteração no disco.
* **Geração de Relatórios:** Produz um relatório Markdown executivo ao final de cada ciclo, detalhando a causa raiz e as ações tomadas.
* **Auto-Commit:** Integração com Git para criar commits automáticos caso os testes sejam aprovados após a intervenção.

## Como Executar

1. Clone o repositório.
2. Instale as dependências requeridas:
   ```bash
   pip install langgraph langchain-google-genai langchain pydantic pytest python-dotenv
   ```
3. Crie um arquivo `.env` na raiz do projeto e insira sua API Key do Google AI Studio:
   ```env
   GEMINI_API_KEY=sua_chave_aqui
   ```
4. (Opcional) Rode o script de configuração para criar um projeto de teste com bug intencional:
   ```bash
   python setup_cobaia.py
   ```
5. Inicie o agente:
   ```bash
   python main.py
   ```

## Roadmap e Próximos Passos
O projeto está em constante evolução. As próximas funcionalidades a serem implementadas são:

- [ ] **Agentic RAG / Web Search:** Permitir que o nó do Analista consulte documentações de APIs externas na internet para resolver erros de integração desconhecidos.
- [ ] **Suporte Multi-Arquivo:** Expandir o nó do Programador para aplicar refatorações em múltiplos arquivos simultaneamente.
- [ ] **Integração CI/CD:** Adaptar o agente para ser acionado via GitHub Actions em Pull Requests falhos.
- [ ] **Suporte a Múltiplas Linguagens:** Generalizar o parser de leitura de diretórios para atuar além do Python (ex: TypeScript, Go, Java).

## Licença
Distribuído sob a licença MIT.