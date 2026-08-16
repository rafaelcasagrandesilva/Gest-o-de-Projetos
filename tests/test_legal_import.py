"""Importação da planilha do Jurídico — o formato oficial e as três regras da carga.

Cobre o que quebra caro se regredir:
1. o arquivo aceito é EXATAMENTE a planilha em uso (aba e cabeçalho verificados);
2. a planilha inclui e atualiza, mas **nunca** exclui nem apaga campo preenchido;
3. reimportar o mesmo arquivo não cria nada e não altera nada (idempotência).
"""

from __future__ import annotations

import asyncio
import io
import unittest
from datetime import date
from decimal import Decimal

import openpyxl

from app.core import permission_codes as pc
from app.models.legal import (
    LegalCase,
    LegalCaseStatus,
    LegalCaseType,
    LegalImportRun,
    LegalPerson,
)
from app.services.legal_import_parser import (
    EXPECTED_HEADER,
    PANEL_ENRICHED_FIELDS,
    SHEET_NAME,
    LegalImportSourceError,
    build_payload,
    parse_agreement,
)
from app.services.legal_import_service import (
    CASE_FIELDS,
    PERSON_FIELDS,
    LegalImportService,
    _coerce,
    _run_row,
)

HEADER = [
    "Nome / Reclamante", "CPF", "Possui Processo?", "Nº do Processo", "Empresa Reclamada",
    "UF / Local", "Contrato / Projeto", "Data de Admissão", "Data de Desligamento",
    "Data Audiência", "Status do Processo (Jurídico)", "Valor Causa / Pedido (R$)",
    "Valor Acordo Processo (R$)", "Valor Rescisão (R$)", "Valor Pago (R$)", "Valor em Aberto (R$)",
    "Saldo FGTS (R$)", "Parcela 1", "Parcela 2", "Parcela 3", "Parcela 4", "Parcela 5",
    "Obs Jurídico", "Obs RH",
]


# Painel de Passivo mínimo, no formato real (bloco `const DATA`), casando pelo nome + tribunal.
PANEL_HTML = (
    "<html><script>\n"
    'const DATA = [{"rte": "Fulano de Tal", "rdo": "M&E ENGENHARIA LTDA", "classe": "trabalhista",'
    ' "trib": "TRT24", "uf": "MS", "cidade": "Dourados", "natureza": "ACAO TRABALHISTA",'
    ' "valor": 30000, "vcons": 30000, "umov": "Sentenca publicada", "umdata": "2025-07-01",'
    ' "url": "https://www.jusbrasil.com.br/processos/9"}];\n'
    "</script></html>"
)


def _row(over: dict[int, object] | None = None) -> list:
    """Linha da planilha; `over` sobrescreve colunas por índice (0-based, como no parser)."""
    base: dict[int, object] = {
        0: "Fulano de Tal", 1: "111.222.333-44", 2: "SIM",
        3: "0000001-11.2025.5.24.0086", 4: "M&E ENGENHARIA", 5: "MS",
        6: "Energisa - C&M Naviraí", 10: "Em andamento",
    }
    base.update(over or {})
    return [base.get(i) for i in range(len(HEADER))]


def _xlsx(rows: list[list], *, sheet: str = SHEET_NAME, header: list | None = None) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(header if header is not None else HEADER)
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Sessão mínima: `_resolve` consulta pessoas e depois processos, nesta ordem."""

    def __init__(self, people: list, cases: list):
        self._queue = [people, cases]
        self.added: list = []

    async def execute(self, _stmt):
        return _FakeResult(self._queue.pop(0) if self._queue else [])

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):  # pragma: no cover - apply() não é exercido aqui
        return None


def _ja_importado(rows: list[list]) -> tuple[list[LegalPerson], list[LegalCase]]:
    """Materializa o estado que uma importação anterior DESTES mesmos dados teria deixado.

    Partir do resultado real (e não de um objeto meio preenchido) é o que torna os testes de
    idempotência honestos: qualquer diferença que aparecer é uma diferença de verdade.
    """
    parsed = build_payload(spreadsheet=_xlsx(rows), spreadsheet_name="planilha.xlsx")
    people, cases = [], []
    for entry in parsed.payload["people"]:
        person = LegalPerson(**{f: _coerce(f, entry.get(f)) for f in PERSON_FIELDS})
        person.is_active = True
        people.append(person)
    for entry in parsed.payload["cases"]:
        case = LegalCase(**{f: _coerce(f, entry.get(f)) for f in CASE_FIELDS})
        case.status = (
            LegalCaseStatus(entry["status"]) if entry["status"] else LegalCaseStatus.EM_ANDAMENTO
        )
        case.case_type = LegalCaseType(entry["case_type"])
        case.is_active = True
        cases.append(case)
    return people, cases


def _resolve(payload_rows: list[list], *, people: list, cases: list):
    parsed = build_payload(spreadsheet=_xlsx(payload_rows), spreadsheet_name="planilha.xlsx")
    session = _FakeSession(people, cases)
    service = LegalImportService.__new__(LegalImportService)
    service.session = session
    resolution = asyncio.run(service._resolve(parsed))
    return parsed, resolution, service


class FormatoOficialTests(unittest.TestCase):
    """A planilha em uso é o contrato: aba e cabeçalho errados param a importação."""

    def test_aba_errada_e_recusada(self):
        with self.assertRaises(LegalImportSourceError) as ctx:
            build_payload(spreadsheet=_xlsx([_row()], sheet="Outra Aba"))
        self.assertIn(SHEET_NAME, str(ctx.exception))

    def test_cabecalho_divergente_e_recusado(self):
        header = list(HEADER)
        header[3] = "Processo"
        with self.assertRaises(LegalImportSourceError) as ctx:
            build_payload(spreadsheet=_xlsx([_row()], header=header))
        self.assertIn("fora do formato oficial", str(ctx.exception))

    def test_cabecalho_ignora_acento_e_caixa(self):
        header = [h.upper() for h in HEADER]
        header[3] = "N. do Processo".upper()  # 'Nº', 'N°' e 'N.' são a mesma coluna
        parsed = build_payload(spreadsheet=_xlsx([_row()], header=header))
        self.assertEqual(len(parsed.payload["cases"]), 1)

    def test_colunas_extras_ao_final_sao_aceitas(self):
        """A planilha pode crescer: só as colunas lidas fazem parte do contrato."""
        parsed = build_payload(
            spreadsheet=_xlsx([_row() + ["coluna nova"]], header=HEADER + ["Coluna Nova"])
        )
        self.assertEqual(len(parsed.payload["people"]), 1)

    def test_arquivo_que_nao_e_xlsx(self):
        with self.assertRaises(LegalImportSourceError):
            build_payload(spreadsheet=b"isto nao e uma planilha")

    def test_todas_as_colunas_lidas_estao_no_contrato(self):
        for index, label in EXPECTED_HEADER.items():
            self.assertEqual(HEADER[index], label, f"coluna {index} divergiu do cabeçalho real")


class LeituraTests(unittest.TestCase):
    def test_status_desconhecido_vira_aviso_e_nao_forca_padrao(self):
        parsed = build_payload(spreadsheet=_xlsx([_row({10: "Rascunho"})]))
        self.assertIsNone(parsed.payload["cases"][0]["status"])
        self.assertTrue(any("não reconhecido" in i.message for i in parsed.issues))

    def test_reclamante_desconhecido_nao_vira_pessoa(self):
        parsed = build_payload(spreadsheet=_xlsx([_row({0: "Desconhecido"})]))
        self.assertEqual(parsed.payload["people"], [])
        self.assertIsNone(parsed.payload["cases"][0]["person_key"])

    def test_numero_repetido_consolida_num_processo(self):
        parsed = build_payload(
            spreadsheet=_xlsx([_row({0: "Desconhecido"}), _row()])
        )
        self.assertEqual(len(parsed.payload["cases"]), 1)
        self.assertEqual(len(parsed.duplicates), 1)
        # A linha identificada prevalece sobre o placeholder.
        self.assertIsNotNone(parsed.payload["cases"][0]["person_key"])

    def test_pessoa_em_varias_linhas_vira_um_cadastro(self):
        outro = _row({3: "0000002-22.2025.5.24.0086"})
        parsed = build_payload(spreadsheet=_xlsx([_row(), outro]))
        self.assertEqual(len(parsed.payload["people"]), 1)
        self.assertEqual(len(parsed.payload["cases"]), 2)

    def test_data_invalida_avisa_em_vez_de_silenciar(self):
        parsed = build_payload(spreadsheet=_xlsx([_row({8: "05/08/2-25"})]))
        self.assertIsNone(parsed.payload["people"][0]["termination_date"])
        self.assertTrue(any("não reconhecida" in i.message for i in parsed.issues))

    def test_tribunal_e_tipo_saem_do_numero_cnj(self):
        parsed = build_payload(spreadsheet=_xlsx([_row({3: "0000001-11.2025.8.26.0100"})]))
        case = parsed.payload["cases"][0]
        self.assertEqual(case["court"], "TJSP")
        self.assertEqual(case["case_type"], "CIVEL")

    def test_acordo_parcelado_soma_o_total(self):
        self.assertEqual(parse_agreement("3 X 2.333,34"), 7000.02)
        self.assertEqual(parse_agreement("1 X 3250,00 e 4 X 2600,00"), 13650.00)
        self.assertIsNone(parse_agreement("a combinar"))

    def test_sem_painel_nao_ha_valores_do_painel(self):
        parsed = build_payload(spreadsheet=_xlsx([_row()]))
        case = parsed.payload["cases"][0]
        self.assertIsNone(case["jusbrasil_url"])
        self.assertIsNone(case["amount_considered"])


class CargaTests(unittest.TestCase):
    """As três regras: cria, atualiza e NUNCA apaga."""

    def test_banco_vazio_cria_tudo(self):
        _, res, _ = _resolve([_row()], people=[], cases=[])
        self.assertEqual([c.created for c in res.people], [True])
        self.assertEqual([c.created for c in res.cases], [True])
        # Status ausente na fonte só assume o padrão na criação.
        self.assertEqual(res.cases[0].values["status"], LegalCaseStatus.EM_ANDAMENTO)
        self.assertIs(res.cases[0].values["is_active"], True)

    def test_reimportacao_nao_altera_nada(self):
        people, cases = _ja_importado([_row()])
        _, res, _ = _resolve([_row()], people=people, cases=cases)
        self.assertEqual(res.people, [])
        self.assertEqual(res.cases, [])
        self.assertEqual((res.people_unchanged, res.cases_unchanged), (1, 1))

    def test_campo_vazio_na_fonte_nao_apaga_valor_existente(self):
        """A planilha sozinha não traz valor considerado nem link — e não pode zerá-los."""
        people, cases = _ja_importado([_row()])
        cases[0].amount_considered = Decimal("5000.00")
        cases[0].jusbrasil_url = "https://jusbrasil.com.br/x"
        cases[0].status = LegalCaseStatus.ACORDO
        _, res, _ = _resolve([_row({10: None})], people=people, cases=cases)
        alterados = res.cases[0].values if res.cases else {}
        self.assertNotIn("amount_considered", alterados)
        self.assertNotIn("jusbrasil_url", alterados)
        # Status em branco na planilha não desfaz o status ajustado na tela.
        self.assertNotIn("status", alterados)

    def test_desativado_na_tela_nao_ressuscita(self):
        people, cases = _ja_importado([_row()])
        cases[0].is_active = False
        _, res, _ = _resolve([_row()], people=people, cases=cases)
        for change in res.cases:
            self.assertNotIn("is_active", change.values)

    def test_registro_ausente_da_planilha_nao_e_removido(self):
        """A planilha é fonte de inclusão e atualização — nunca instrução de exclusão."""
        orfa = LegalPerson(full_name="Quem Saiu da Planilha", cpf="000.000.000-00")
        orfao = LegalCase(case_number="0000009-99.2025.5.24.0086")
        _, res, service = _resolve([_row()], people=[orfa], cases=[orfao])
        alvos = [c.target for c in res.people + res.cases]
        self.assertNotIn(orfa, alvos)
        self.assertNotIn(orfao, alvos)
        self.assertEqual(service.session.added, [])  # nada foi tocado

    def test_valor_alterado_e_detectado_uma_vez(self):
        people, cases = _ja_importado([_row()])
        _, res, _ = _resolve([_row({14: 250.5})], people=people, cases=cases)
        self.assertEqual([c.changed for c in res.cases], [["Valor pago"]])

    def test_decimal_do_banco_nao_conta_como_alteracao(self):
        """Numeric(14,2) volta como Decimal: comparar com float não pode gerar update fantasma."""
        people, cases = _ja_importado([_row({14: 250.50})])
        self.assertEqual(cases[0].amount_paid, 250.5)
        cases[0].amount_paid = Decimal("250.50")
        _, res, _ = _resolve([_row({14: 250.50})], people=people, cases=cases)
        self.assertEqual(res.cases, [])

    def test_data_do_banco_nao_conta_como_alteracao(self):
        people, cases = _ja_importado([_row({7: "01/03/2024"})])
        self.assertEqual(people[0].admission_date, date(2024, 3, 1))
        _, res, _ = _resolve([_row({7: "01/03/2024"})], people=people, cases=cases)
        self.assertEqual(res.people, [])

    def test_homonimos_sem_cpf_nao_sao_atualizados_no_escuro(self):
        a = LegalPerson(full_name="Fulano de Tal")
        b = LegalPerson(full_name="Fulano de Tal")
        _, res, _ = _resolve([_row({1: None})], people=[a, b], cases=[])
        self.assertEqual(res.people, [])
        self.assertEqual(len(res.conflicts), 1)

    def test_cadastro_sem_cpf_recebe_o_cpf_da_planilha(self):
        people, cases = _ja_importado([_row({1: None})])
        _, res, _ = _resolve([_row()], people=people, cases=cases)
        self.assertEqual([c.changed for c in res.people], [["CPF"]])


class PainelFonteHistoricaTests(unittest.TestCase):
    """O painel enriquece a PRIMEIRA carga; depois o banco é dono desses campos.

    A regra é mais forte que "vazio não apaga": numa importação só-planilha esses campos não são
    reescritos nem quando a planilha tem um valor — que seria pior (`defendant_name`, `company`).
    """

    # Como estava o processo depois da carga inicial COM painel.
    def _enriquecido(self):
        people, cases = _ja_importado([_row()])
        case = cases[0]
        case.jusbrasil_url = "https://www.jusbrasil.com.br/processos/1"
        case.amount_considered = Decimal("12345.67")
        case.amount_claimed = Decimal("20000.00")
        case.city = "Campo Grande"
        case.nature = "AÇÃO TRABALHISTA"
        case.court = "TRT24"
        case.last_movement = "Audiência designada"
        case.last_movement_date = date(2025, 6, 10)
        case.defendant_name = "M&E CONSULTORIA LTDA"
        case.company = "M&E CONSULTORIA LTDA"
        return people, cases

    def test_so_planilha_nao_reescreve_nada_do_painel(self):
        people, cases = self._enriquecido()
        # A planilha traz OUTRO reclamado na coluna "Empresa Reclamada" — não pode prevalecer.
        _, res, _ = _resolve([_row({4: "Energisa MS"})], people=people, cases=cases)
        alterados = set(res.cases[0].values) if res.cases else set()
        self.assertEqual(alterados & PANEL_ENRICHED_FIELDS, set())

    def test_so_planilha_nao_troca_entidade_do_grupo_por_tomadora(self):
        people, cases = self._enriquecido()
        _, res, _ = _resolve([_row({4: "Energisa MS"})], people=people, cases=cases)
        self.assertEqual(res.cases, [], "company do grupo M&E não pode virar a concessionária")

    def test_so_planilha_ainda_corrige_empresa_de_terceiro(self):
        """A proteção é do grupo M&E; empresa de terceiro continua atualizável pela planilha."""
        people, cases = self._enriquecido()
        cases[0].company = "Energisa MS"
        _, res, _ = _resolve([_row({4: "Enel Brasil S.A"})], people=people, cases=cases)
        self.assertEqual([c.changed for c in res.cases], [["Empresa"]])

    def test_com_painel_os_campos_voltam_a_ser_atualizaveis(self):
        people, cases = self._enriquecido()
        parsed = build_payload(
            spreadsheet=_xlsx([_row()]),
            panel=PANEL_HTML,
            spreadsheet_name="planilha.xlsx",
            panel_name="painel_passivo.html",
        )
        service = LegalImportService.__new__(LegalImportService)
        service.session = _FakeSession(people, cases)
        res = asyncio.run(service._resolve(parsed))
        mudou = set(res.cases[0].values) if res.cases else set()
        self.assertTrue(mudou & PANEL_ENRICHED_FIELDS, "com painel, os campos dele são gravados")

    def test_criacao_sem_painel_aproveita_o_que_a_planilha_tem(self):
        """Num registro NOVO não há o que preservar — o reclamado vem da planilha."""
        _, res, _ = _resolve([_row({4: "Energisa MS"})], people=[], cases=[])
        self.assertEqual(res.cases[0].values["defendant_name"], "Energisa MS")

    def test_painel_ausente_e_reconhecido_no_payload(self):
        self.assertFalse(build_payload(spreadsheet=_xlsx([_row()])).panel_present)


class HistoricoTests(unittest.TestCase):
    def test_linha_do_historico_reflete_o_relatorio(self):
        parsed = build_payload(spreadsheet=_xlsx([_row()]), spreadsheet_name="planilha.xlsx")
        service = LegalImportService.__new__(LegalImportService)
        service.session = _FakeSession([], [])
        resolution = asyncio.run(service._resolve(parsed))
        report = service._report(parsed, resolution, applied=True)

        run = _run_row(report, actor=None, elapsed_ms=42)
        self.assertEqual(run.spreadsheet_name, "planilha.xlsx")
        self.assertIsNone(run.panel_name)  # só planilha
        self.assertEqual((run.people_new, run.cases_new), (1, 1))
        self.assertEqual(run.rows_read, 1)
        self.assertEqual(run.duration_ms, 42)

    def test_historico_nao_guarda_valor_monetario(self):
        colunas = {c.name for c in LegalImportRun.__table__.columns}
        self.assertEqual(colunas & {"amount_considered", "amount_claimed", "total"}, set())


class PermissaoTests(unittest.TestCase):
    def test_recurso_proprio_do_menu_importacoes(self):
        self.assertIn(pc.LEGAL_IMPORTS_CREATE, pc.LEGAL_MODULE_CODES)
        self.assertIn(pc.LEGAL_IMPORTS_LIST, pc.ACTIVE_PERMISSION_CODES)
        # Importar concede ver a aba, e concede acesso ao workspace (como os demais menus).
        self.assertIn(pc.LEGAL_IMPORTS_LIST, pc.expand_permissions({pc.LEGAL_IMPORTS_CREATE}))
        self.assertIn(pc.LEGAL_IMPORTS_CREATE, pc.LEGAL_WORKSPACE_GRANTING)

    def test_perfil_somente_leitura_nao_importa(self):
        efetivas = pc.expand_permissions(pc.PRESET_CONSULTA)
        self.assertNotIn(pc.LEGAL_IMPORTS_CREATE, efetivas)
        self.assertNotIn(pc.LEGAL_IMPORTS_LIST, efetivas)

    def test_quem_administra_o_modulo_importa(self):
        for preset in (pc.PRESET_ADMIN, pc.PRESET_GESTOR):
            self.assertIn(pc.LEGAL_IMPORTS_CREATE, pc.expand_permissions(preset))

    def test_ler_processos_nao_concede_importar(self):
        efetivas = pc.expand_permissions({pc.LEGAL_CASES_UPDATE, pc.LEGAL_PERSONS_UPDATE})
        self.assertNotIn(pc.LEGAL_IMPORTS_CREATE, efetivas)

    def test_ver_o_historico_nao_concede_importar(self):
        self.assertNotIn(pc.LEGAL_IMPORTS_CREATE, pc.expand_permissions({pc.LEGAL_IMPORTS_LIST}))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
