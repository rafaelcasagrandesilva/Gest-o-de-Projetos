#!/usr/bin/env python3
"""Gera o dataset LOCAL do Workspace Jurídico (`app/scripts/data/legal_seed.json`).

Este script é apenas um INVÓLUCRO de linha de comando: toda a transformação vive em
`app/services/legal_import_parser.py`, o mesmo módulo que o importador da tela executa. Rodar
aqui ou importar pela interface produz exatamente o mesmo resultado — é o que garante que a
produção fique idêntica ao ambiente de testes.

O JSON gerado serve ao desenvolvimento (`python manage.py seed_legal`, sem depender dos
arquivos originais) e **não é versionado**: `app/scripts/data/` está no `.gitignore` porque o
arquivo carrega CPF, nome, rescisão e FGTS de pessoas reais. Em produção a carga é feita pela
importação da planilha na tela.

Uso:
    python scripts/build_legal_seed.py \
        --xlsx "~/Downloads/PLANILHA UNIFICADA - PROCESSOS E DEMITIDOS 2.xlsx" \
        --painel "~/Documents/Work/JusBrasil/jusbrasil_scraper/output/painel_passivo.html"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.services.legal_import_parser import (  # noqa: E402
    LegalImportSourceError,
    build_payload,
)

DEFAULT_OUT = REPO_ROOT / "app" / "scripts" / "data" / "legal_seed.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", required=True, help="Planilha unificada (.xlsx)")
    parser.add_argument("--painel", required=True, help="painel_passivo.html")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="JSON de saída")
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx).expanduser()
    panel_path = Path(args.painel).expanduser()
    out_path = Path(args.out).expanduser()

    try:
        parsed = build_payload(
            spreadsheet=xlsx_path.read_bytes(),
            panel=panel_path.read_bytes(),
            spreadsheet_name=xlsx_path.name,
            panel_name=panel_path.name,
        )
    except LegalImportSourceError as exc:
        raise SystemExit(str(exc)) from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(parsed.payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    cases = parsed.payload["cases"]
    with_url = sum(1 for c in cases if c["jusbrasil_url"])
    with_value = sum(1 for c in cases if c["amount_claimed"] is not None)
    considered = sum(c["amount_considered"] or 0 for c in cases)
    print(f"{out_path}")
    print(f"  linhas lidas ....... {parsed.rows_read}")
    print(f"  pessoas ............ {len(parsed.payload['people'])}")
    print(f"  processos .......... {len(cases)}")
    print(f"  com link JusBrasil . {with_url}")
    print(f"  com valor da causa . {with_value}")
    print(f"  valor considerado .. R$ {considered:,.2f}")
    print(f"  duplicados ......... {len(parsed.duplicates)}")
    print(f"  avisos/erros ....... {len(parsed.issues)}")
    for issue in parsed.issues:
        print(f"    [{issue.level}] linha {issue.row}: {issue.message}")


if __name__ == "__main__":
    main()
