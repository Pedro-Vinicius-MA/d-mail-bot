"""D-MAIL — busca de notícias grátis (Google News RSS + DuckDuckGo, sem chave de API).

O template só pesquisa com serviços pagos (AskNews, Perplexity, Exa). Sem eles,
o LLM "pesquisa" de memória e não sabe o que aconteceu ontem. Aqui buscamos
notícias e páginas recentes sobre a pergunta e entregamos o texto ao modelo,
que só então resume.

Fontes, na ordem:
  1. Google News RSS: estável, sem chave, aceita consultas em linguagem natural.
  2. DuckDuckGo (notícias e web): complementa quando funciona; costuma bloquear
     servidores do GitHub, então é só reforço.

Se tudo falhar (limite, rede), devolve vazio e o bot segue sem busca — nunca
derruba a previsão.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

_INICIOS = re.compile(
    r"^(will|what|which|when|how many|how much|who|whether|by|before|is|are|does|do)\b\s*",
    re.IGNORECASE,
)


def _consulta_curta(titulo: str) -> str:
    """Tira o jeito de pergunta ("Will ... ?") e parênteses longos, que atrapalham a busca."""
    t = titulo.strip().rstrip("?").strip()
    t = re.sub(r"\([^)]{40,}\)", "", t)
    for _ in range(2):
        t = _INICIOS.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:160] or titulo[:160]


def _google_news(consulta: str, max_itens: int = 10) -> list[str]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": consulta, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (forecasting research bot)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        raiz = ET.fromstring(r.read())
    linhas = []
    for item in raiz.iter("item"):
        titulo = html.unescape(item.findtext("title") or "")
        data = (item.findtext("pubDate") or "")[:16]
        fonte = item.findtext("source") or ""
        descricao = re.sub(r"<[^>]+>", " ", html.unescape(item.findtext("description") or ""))
        descricao = re.sub(r"\s+", " ", descricao).strip()[:300]
        linha = f"- [{data}] {fonte}: {titulo}"
        if descricao and descricao not in titulo:
            linha += f"\n  {descricao}"
        linhas.append(linha)
        if len(linhas) >= max_itens:
            break
    return linhas


def _ddg(consulta: str, max_noticias: int = 6, max_paginas: int = 4) -> list[str]:
    try:
        from ddgs import DDGS
    except Exception:  # biblioteca ausente
        return []
    linhas: list[str] = []
    with DDGS() as d:
        for r in d.news(consulta, max_results=max_noticias) or []:
            linhas.append(
                f"- [{(r.get('date') or '')[:10]}] {r.get('source', '')}: {r.get('title', '')}\n"
                f"  {r.get('body', '')[:300]}"
            )
        for r in d.text(consulta, max_results=max_paginas) or []:
            linhas.append(f"- (web) {r.get('title', '')}\n  {r.get('body', '')[:300]}")
    return linhas


def _buscar(titulo: str) -> str:
    consulta = _consulta_curta(titulo)
    partes: list[str] = []
    try:
        noticias = _google_news(consulta)
        if noticias:
            partes.append("Google News:\n" + "\n".join(noticias))
    except Exception as e:
        logger.warning(f"Google News falhou para '{consulta[:80]}': {e}")
    try:
        extras = _ddg(consulta)
        if extras:
            partes.append("DuckDuckGo:\n" + "\n".join(extras))
    except Exception as e:  # limite de requisições, rede etc.
        logger.warning(f"Busca DuckDuckGo falhou para '{consulta[:80]}': {e}")
    return "\n\n".join(partes)


async def buscar_contexto(titulo: str) -> str:
    """Notícias e páginas recentes sobre o título da pergunta (texto pronto para o prompt)."""
    texto = await asyncio.to_thread(_buscar, titulo)
    if not texto:
        return ""
    return (
        "Resultados de busca recentes sobre a pergunta — use como evidência, "
        "citando datas, e desconfie de fontes fracas:\n" + texto
    )
