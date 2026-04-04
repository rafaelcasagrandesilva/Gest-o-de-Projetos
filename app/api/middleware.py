from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


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

