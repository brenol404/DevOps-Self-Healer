"""Cliente opcional do hybrid-rag-mcp (HTTP) para contexto semântico.

O analyst já recebe os arquivos do traceback; este módulo busca trechos
*similares* além deles (chamadores, padrões parecidos, docs). Uso:

    RAG_URL=http://127.0.0.1:8000  (servidor com `ingest` já rodado no repo-alvo)

Sem RAG_URL, sem lib `mcp` ou com servidor fora do ar: retorna "" e o fluxo
segue idêntico (degradação graciosa — nunca quebra o diagnóstico).
Requer `pip install mcp` (dependência opcional) + `RAG_AUTH_TOKEN` se o
servidor exigir bearer.
"""

from __future__ import annotations

import asyncio
import os


def _mcp_search(base_url: str, query: str, top_k: int, timeout: float) -> str:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    http_client = None
    token = os.getenv("RAG_AUTH_TOKEN", "").strip()
    if token:
        import httpx

        http_client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}, timeout=timeout
        )

    async def _run() -> str:
        kwargs = {"http_client": http_client} if http_client is not None else {}
        async with streamable_http_client(f"{base_url}/mcp", **kwargs) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("search", {"query": query, "top_k": top_k})
                return "\n".join(
                    getattr(c, "text", "") for c in result.content if hasattr(c, "text")
                )

    return asyncio.run(asyncio.wait_for(_run(), timeout=timeout))


def fetch_rag_context(query: str, top_k: int = 5) -> str:
    """Trechos semanticamente similares do repo-alvo, ou "" se indisponível."""
    base_url = os.getenv("RAG_URL", "").strip().rstrip("/")
    if not base_url or not query.strip():
        return ""
    try:
        top_k = int(os.getenv("RAG_TOP_K", str(top_k)))
        timeout = float(os.getenv("RAG_TIMEOUT_SEC", "120"))
    except ValueError:
        top_k, timeout = 5, 120.0
    try:
        return _mcp_search(base_url, query.strip()[:2000], top_k, timeout).strip()
    except Exception:
        return ""
