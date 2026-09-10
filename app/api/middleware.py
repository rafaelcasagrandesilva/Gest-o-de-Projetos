from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.utils.memory import current_rss_bytes, release_free_memory

logger = logging.getLogger(__name__)


class ForwardedProtoMiddleware(BaseHTTPMiddleware):
    """
    Ajusta scope['scheme'] a partir de X-Forwarded-Proto (proxy HTTPS: Railway, etc.).

    Sem isso, redirect_slashes e qualquer URL derivada de request.base_url usam
    scheme=http no hop interno proxy→container, gerando 307 Location: http://...
    e mixed-content no navegador.

    O Uvicorn com --proxy-headers só confia nesses headers se o peer estiver em
    --forwarded-allow-ips (padrão frequentemente só 127.0.0.1), o que falha no Railway.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        raw = request.headers.get("x-forwarded-proto")
        if raw:
            first = raw.split(",")[0].strip().lower()
            if first in ("https", "http"):
                request.scope["scheme"] = first
        return await call_next(request)


class AuthStateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # O usuário autenticado é anexado em request.state.user pela dependency get_current_user.
        # Aqui garantimos que state.user exista para código que queira ler sem depender do auth.
        if not hasattr(request.state, "user"):
            request.state.user = None
        return await call_next(request)


class MemoryReclaimMiddleware(BaseHTTPMiddleware):
    """Devolve ao SO a memória que uma requisição pesada reservou.

    O Railway cobra **MB × minuto**: memória que o Python liberou mas não devolveu ao sistema
    continua sendo paga a cada minuto até o processo reiniciar. Uma exportação de relatório
    ou uma importação de planilha sobe o piso do processo e ele fica lá — cerca de US$ 0,03
    por dia a cada 100 MB. Ver `app/utils/memory.py`.

    O gatilho é o CRESCIMENTO da requisição, não o consumo absoluto: só chama `malloc_trim`
    quando aquela requisição em particular fez a memória residente subir além do limiar. Com
    isso o tráfego normal (abrir telas, salvar formulário) não paga nada — nem a leitura de
    /proc, que é um arquivo minúsculo, nem a varredura das listas de livres.

    Roda DEPOIS da resposta ser montada, quando os objetos intermediários da exportação já
    viraram lixo. O corpo da resposta ainda está vivo aqui, mas ele não é o problema: o que
    retém memória é o andaime (a planilha do openpyxl, o documento do reportlab), e esse já
    foi liberado.

    Fora do Linux/glibc é no-op — `current_rss_bytes()` devolve `None` e nada acontece.
    """

    def __init__(self, app, min_growth_mb: int = 32) -> None:
        super().__init__(app)
        #: 0 desativa. O padrão ignora o ruído normal e pega exportação/importação de verdade.
        self._min_growth = max(0, min_growth_mb) * 1024 * 1024

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._min_growth == 0:
            return await call_next(request)

        antes = current_rss_bytes()
        response = await call_next(request)
        if antes is None:
            return response  # sem /proc (macOS): nada a medir nem a devolver

        depois = current_rss_bytes()
        if depois is not None and depois - antes >= self._min_growth:
            if release_free_memory():
                recuperado = depois - (current_rss_bytes() or depois)
                logger.info(
                    "Memória devolvida ao SO após %s %s: +%.0f MB na requisição, -%.0f MB recuperados.",
                    request.method,
                    request.url.path,
                    (depois - antes) / 1024 / 1024,
                    recuperado / 1024 / 1024,
                )
        return response
