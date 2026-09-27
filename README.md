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
   pip install -r requirements.txt
   ```
3. Crie um arquivo `.env` na raiz do projeto e insira sua API Key do Google AI Studio:
   ```env
   GEMINI_API_KEY=sua_chave_aqui
   ```

### Contexto semântico via RAG (opcional)

Por padrão o analyst usa só os arquivos do traceback. Apontando para um
[hybrid-rag-mcp](https://github.com/brenol404/hybrid-rag-mcp) com o repo-alvo
indexado, ele recebe também trechos *similares* além do traceback:

```bash
# terminal 1: servidor RAG com o repo-alvo indexado
python -m hybrid_rag_mcp --transport http --port 8000
# (via tool `ingest`, indexe o diretório do repo-alvo)

# terminal 2: healer com RAG ligado
export RAG_URL=http://127.0.0.1:8000  # + RAG_TOP_K / RAG_TIMEOUT_SEC / RAG_AUTH_TOKEN opcionais
python main.py
```

Sem `RAG_URL` (ou com servidor fora do ar), o diagnóstico segue idêntico —
degradação graciosa, nunca quebra o fluxo.
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
- [x] **Auto-Rollback (Botão de Pânico):** Executar um `git reset --hard` para restaurar o projeto caso o agente esgote as tentativas de teste e não consiga consertar o bug.
- [x] **Nó de Code Reviewer:** Inserir um Agente Revisor no LangGraph para analisar se a correção segue princípios de Clean Code/SOLID antes de ser aplicada.

### Fase 2: Escalonamento e Performance
- [x] **Recuperação seletiva de contexto (Traceback-RAG):** em vez de ler o repositório inteiro, o parser extrai do traceback só os arquivos afetados (economia de tokens). Busca semântica/AST segue como evolução futura.
- [x] **Suporte Multi-Modelo Agnostico:** Tornar o projeto flexível para ler variáveis do `.env` e rodar em qualquer LLM (OpenAI, Anthropic, Gemini) ou até modelos rodando 100% locais (Ollama).

### Fase 3: Proatividade e Integração de Equipe
- [x] **Geração Proativa de Testes:** Capacitar o Agente a não apenas consertar o código, mas escrever novos casos de teste (`test_*.py`) garantindo que a mesma falha nunca se repita.
- [x] **Notificações Webhook (Slack/Discord):** Configurar o Agente para disparar uma mensagem no chat da equipe de desenvolvimento após consertar um erro via CI/CD.

## Licença
Distribuído sob a licença MIT.