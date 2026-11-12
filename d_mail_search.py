"""D-MAIL — busca de notícias grátis (DuckDuckGo, sem chave de API).

O template só pesquisa com serviços pagos (AskNews, Perplexity, Exa). Sem eles,
o LLM "pesquisa" de memória e não sabe o que aconteceu ontem. Aqui buscamos
notícias e páginas recentes sobre a pergunta e entregamos o texto ao modelo,
que só então resume. Se a busca falhar (limite, rede), devolve vazio e o bot
segue sem ela — nunca derruba a previsão.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def _buscar(consulta: str, max_noticias: int = 8, max_paginas: int = 5) -> str:
    try:
        from ddgs import DDGS
    except Exception:  # biblioteca ausente
        return ""
    linhas: list[str] = []
    try:
        with DDGS() as d:
            for r in d.news(consulta, max_results=max_noticias) or []:
                linhas.append(
                    f"- [{(r.get('date') or '')[:10]}] {r.get('source', '')}: {r.get('title', '')}\n"
                    f"  {r.get('body', '')[:400]}\n  {r.get('url', '')}"
                )
            for r in d.text(consulta, max_results=max_paginas) or []:
                linhas.append(
                    f"- (web) {r.get('title', '')}\n  {r.get('body', '')[:400]}\n  {r.get('href', '')}"
                )
    except Exception as e:  # limite de requisições, rede etc.
        logger.warning(f"Busca DuckDuckGo falhou para '{consulta[:80]}': {e}")
    return "\n".join(linhas)


async def buscar_contexto(titulo: str) -> str:
    """Notícias e páginas recentes sobre o título da pergunta (texto pronto para o prompt)."""
    consulta = titulo.strip().rstrip("?")[:200]
    texto = await asyncio.to_thread(_buscar, consulta)
    if not texto:
        return ""
    return (
        "Resultados de busca recentes (DuckDuckGo) sobre a pergunta — use como evidência, "
        "citando datas, e desconfie de fontes fracas:\n" + texto
    )
