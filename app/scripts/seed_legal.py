"""Carga do Workspace Jurídico para DESENVOLVIMENTO.

Em produção a carga oficial é a **importação da planilha** pela tela (Administração →
Importações). Este comando existe só para levantar um ambiente local:

    python manage.py seed_legal --xlsx planilha.xlsx --painel painel_passivo.html
    python manage.py seed_legal --file /caminho/legal_seed.json    # JSON já gerado

O caminho PADRÃO (`app/scripts/data/legal_seed.json`) não é versionado — o diretório inteiro
está no `.gitignore`, porque o arquivo carrega CPF, nome, rescisão e FGTS de pessoas reais.
Gere-o localmente com `scripts/build_legal_seed.py` se quiser o atalho sem argumentos.

Ele NÃO tem lógica própria: monta o payload (pelo JSON ou pelo parser oficial) e entrega ao
`LegalImportService`, o mesmo serviço que a importação da tela executa. Um fluxo só de
transformação e de escrita — logo, seed e importação não podem divergir.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.database.session import AsyncSessionLocal
from app.schemas.legal_import import LegalImportReport
from app.services.legal_import_parser import ParsedSources, build_payload
from app.services.legal_import_service import LegalImportService

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent / "data" / "legal_seed.json"


async def seed_legal(
    data_file: Path | None = None,
    *,
    xlsx: Path | None = None,
    panel: Path | None = None,
) -> LegalImportReport:
    if xlsx is not None:
        parsed = build_payload(
            spreadsheet=xlsx.read_bytes(),
            panel=panel.read_bytes() if panel else None,
            spreadsheet_name=xlsx.name,
            panel_name=panel.name if panel else None,
        )
    else:
        path = data_file or DATA_FILE
        if not path.exists():
            raise FileNotFoundError(
                f"Arquivo de seed não encontrado: {path}.\n"
                "Este JSON não é versionado (contém dados pessoais). Use as fontes originais:\n"
                "  python manage.py seed_legal --xlsx planilha.xlsx --painel painel_passivo.html\n"
                "ou gere o JSON localmente com scripts/build_legal_seed.py.\n"
                "Em PRODUÇÃO a carga é feita pela tela: Jurídico → Administração → Importações."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        parsed = ParsedSources(payload=payload)

    async with AsyncSessionLocal() as session:
        report = await LegalImportService(session).apply(parsed)

    s = report.summary
    logger.info(
        "seed_legal: pessoas +%d/~%d · processos +%d/~%d (sem alteração: %d)",
        s.people_new,
        s.people_updated,
        s.cases_new,
        s.cases_updated,
        s.people_unchanged + s.cases_unchanged,
    )
    return report


__all__ = ["seed_legal", "DATA_FILE"]
