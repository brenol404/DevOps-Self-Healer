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

## Roadmap e Próximos Passos (V2)
O roadmap inicial foi concluído! O novo foco (Versão 2.0) é voltado para segurança, escalabilidade em grandes repositórios e uso nível Enterprise:

### Fase 1: Segurança e Qualidade do Código
- [ ] **Auto-Rollback (Botão de Pânico):** Executar um `git reset --hard` para restaurar o projeto caso o agente esgote as tentativas de teste e não consiga consertar o bug.
- [ ] **Nó de Code Reviewer:** Inserir um Agente Revisor no LangGraph para analisar se a correção segue princípios de Clean Code/SOLID antes de ser aplicada.

### Fase 2: Escalonamento e Performance
- [ ] **Code RAG para Repositórios Massivos:** Resolver o limite de tokens do LLM parando de ler o repositório inteiro e utilizando busca semântica ou AST (Abstract Syntax Tree) para fornecer apenas o contexto estritamente necessário.
- [ ] **Suporte Multi-Modelo Agnostico:** Tornar o projeto flexível para ler variáveis do `.env` e rodar em qualquer LLM (OpenAI, Anthropic, Gemini) ou até modelos rodando 100% locais (Ollama).

### Fase 3: Proatividade e Integração de Equipe
- [ ] **Geração Proativa de Testes:** Capacitar o Agente a não apenas consertar o código, mas escrever novos casos de teste (`test_*.py`) garantindo que a mesma falha nunca se repita.
- [ ] **Notificações Webhook (Slack/Discord):** Configurar o Agente para disparar uma mensagem no chat da equipe de desenvolvimento após consertar um erro via CI/CD.

## Licença
Distribuído sob a licença MIT.