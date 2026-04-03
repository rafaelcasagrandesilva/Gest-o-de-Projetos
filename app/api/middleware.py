from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class AuthStateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # O usuário autenticado é anexado em request.state.user pela dependency get_current_user.
        # Aqui garantimos que state.user exista para código que queira ler sem depender do auth.
        if not hasattr(request.state, "user"):
            request.state.user = None
        return await call_next(request)

