"""Apresentação (Presenter) dos Eventos de Liquidação — fonte ÚNICA de formatação no backend.

Reutilizado pelo resolver de descrição do Ledger, pelo Excel e pelo PDF. A API devolve dados
ESTRUTURADOS (número do evento, lista de NFs…); a montagem das strings amigáveis fica só aqui,
evitando duplicação de lógica de apresentação. Não contém regra de negócio.
"""

from __future__ import annotations

from collections.abc import Iterable

_EVENT_PREFIX = "LQ"


def event_code(number: int | None) -> str | None:
    """Identificador operacional amigável do evento. Ex.: 42 -> "LQ-000042"."""
    if number is None:
        return None
    return f"{_EVENT_PREFIX}-{int(number):06d}"


def nf_summary(nf_numbers: Iterable[str | None]) -> str:
    """Resumo legível das NFs de um evento. "NF 3397" (uma) ou "NFs 3351, 3353, 3364" (várias)."""
    seen: list[str] = []
    for n in nf_numbers:
        s = str(n).strip() if n is not None else ""
        if s and s not in seen:
            seen.append(s)
    if not seen:
        return "—"
    if len(seen) == 1:
        return f"NF {seen[0]}"
    return "NFs " + ", ".join(seen)


def ledger_settlement_label(
    *, code: str | None, nf_number: str | None, client_name: str | None
) -> str:
    """Descrição de uma liquidação no Extrato do Repasse (nunca expõe UUID).

    Com evento: "Liquidação LQ-000018 • NF 3397 • Cliente". Sem evento (lançamento antigo):
    "NF 3397 • Cliente" (ou "Liquidação" se a NF não puder ser resolvida)."""
    nf = str(nf_number).strip() if nf_number else ""
    client = str(client_name).strip() if client_name else ""
    nf_part = f"NF {nf}" if nf else ""
    parts = [p for p in (nf_part, client) if p]
    tail = " • ".join(parts)
    if code:
        return f"Liquidação {code}" + (f" • {tail}" if tail else "")
    return tail or "Liquidação"
