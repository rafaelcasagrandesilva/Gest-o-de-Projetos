"""Lista os anexos registrados no banco cujo arquivo NÃO existe em disco.

Mesmo núcleo do endpoint `GET /api/v1/admin/storage/missing-files`
(`app/services/storage_report_service.py`), para uso por linha de comando.

Uso:
    python -m scripts.relatorio_arquivos_ausentes
    python -m scripts.relatorio_arquivos_ausentes --csv /tmp/faltando.csv
    python -m scripts.relatorio_arquivos_ausentes --csv /tmp/tudo.csv --todos

IMPORTANTE: precisa rodar NO MESMO ambiente em que os arquivos vivem. Em produção,
dentro do container (ex.: `railway ssh python -m scripts.relatorio_arquivos_ausentes`);
rodar na máquina local com a DATABASE_URL de produção compara o banco remoto com o
disco local e acusa tudo como ausente.

Somente leitura: não escreve no banco nem toca nos arquivos.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path

from app.database.session import AsyncSessionLocal
from app.services.storage_report_service import collect_attachments, missing_files_report


async def _coletar() -> tuple[dict, list]:
    async with AsyncSessionLocal() as session:
        relatorio = await missing_files_report(session)
        achados = await collect_attachments(session)
    return relatorio, achados


def _imprimir(relatorio: dict) -> None:
    print("Diretórios em uso:")
    for nome, caminho in relatorio["diretorios"].items():
        print(f"  {nome:<24} = {caminho}")
    print()

    for linha in relatorio["resumo"]:
        print(f"{linha['tipo']}: {linha['ausentes']} ausente(s) de {linha['total']} registro(s)")
        for a in relatorio["ausentes"]:
            if a["tipo"] == linha["tipo"]:
                print(f"    • {a['onde']} | {a['titulo']} | {a['arquivo']} | enviado em {a['enviado_em']}")
        print()

    print(f"TOTAL: {relatorio['total_ausentes']} arquivo(s) para reenviar de {relatorio['total_registros']} registro(s).")


def _exportar_csv(achados: list, destino: Path, todos: bool) -> None:
    linhas = achados if todos else [a for a in achados if not a.existe]
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Tipo", "Onde", "Título", "Arquivo", "Enviado em", "Situação", "Caminho esperado"])
        for a in linhas:
            w.writerow(
                [a.tipo, a.onde, a.titulo, a.arquivo, a.enviado_em, "OK" if a.existe else "AUSENTE", a.caminho]
            )
    print(f"CSV gravado em {destino} ({len(linhas)} linha(s)).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Anexos registrados no banco sem arquivo em disco")
    parser.add_argument("--csv", default=None, help="Caminho para exportar o resultado em CSV")
    parser.add_argument("--todos", action="store_true", help="Incluir também os anexos OK no CSV")
    args = parser.parse_args()

    relatorio, achados = asyncio.run(_coletar())
    _imprimir(relatorio)
    if args.csv:
        _exportar_csv(achados, Path(args.csv), args.todos)


if __name__ == "__main__":
    main()
