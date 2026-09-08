"""Motor de saldo do Endividamento (núcleo puro `app/services/debt_accrual.py`).

O caso central é REAL: a planilha de controle de um acordo com fornecedor que o financeiro
mantinha fora do sistema — 28 competências, 04/2024 a 07/2026, com mudança de taxa, dois
aportes, cinco parcelas pagas, um pagamento avulso de R$ 100.000 e quinze meses de
capitalização. Se o motor reproduz essa planilha, ele reproduz o que a empresa já faz à mão.
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from app.services.debt_accrual import (
    APORTE,
    ABATIMENTO,
    ENCARGO_MANUAL,
    LedgerEvent,
    RateChange,
    build_ledger,
    compute_indicators,
    rate_for,
)

D = Decimal


def comp(y: int, m: int) -> date:
    return date(y, m, 1)


# --------------------------------------------------------------------------- #
# A planilha real                                                             #
# --------------------------------------------------------------------------- #

PLANILHA = dict(
    principal=D("100000.00"),
    origin_month=comp(2024, 4),
    rates=[
        RateChange(valid_from=comp(2024, 4), monthly_rate=D("0.03")),
        RateChange(valid_from=comp(2026, 1), monthly_rate=D("0.015")),
    ],
    events=[
        LedgerEvent(competencia=comp(2025, 1), kind=APORTE, amount=D("28000.00")),
        LedgerEvent(competencia=comp(2025, 8), kind=APORTE, amount=D("60000.00")),
    ],
    payments={
        comp(2024, 4): D("15500.00"),
        comp(2024, 5): D("15125.00"),
        comp(2024, 6): D("14750.00"),
        comp(2024, 7): D("14375.00"),
        comp(2024, 8): D("14000.00"),
        comp(2025, 11): D("100000.00"),
    },
)

# Saldo final de cada competência conforme a PLANILHA (coluna "Saldo Final").
# A planilha arredonda cada linha para exibição mas encadeia o cálculo em precisão cheia; o
# motor arredonda a cada mês (convenção financeira do resto do sistema, `_money`). Daí uma
# diferença que chega a 2 centavos no meio da série — conferida e aceita.
SALDO_PLANILHA = {
    1: "87500.00", 2: "75000.00", 3: "62500.00", 4: "50000.00", 5: "37500.00",
    6: "38625.00", 7: "39783.75", 8: "40977.26", 9: "42206.58", 10: "71472.78",
    11: "73616.96", 12: "75825.47", 13: "78100.23", 14: "80443.24", 15: "82856.54",
    16: "85342.23", 17: "147902.50", 18: "152339.58", 19: "156909.76", 20: "61617.06",
    21: "63465.57", 22: "64417.55", 23: "65383.82", 24: "66364.57", 25: "67360.04",
    26: "68370.44", 27: "69396.00", 28: "70436.94",
}

TOLERANCIA_PLANILHA = D("0.02")


class PlanilhaRealTests(unittest.TestCase):
    """O motor tem que reproduzir a planilha do financeiro, linha a linha."""

    def setUp(self) -> None:
        self.lines = build_ledger(through=comp(2026, 7), **PLANILHA)
        self.ind = compute_indicators(self.lines, principal=PLANILHA["principal"])

    def test_uma_linha_por_competencia(self) -> None:
        self.assertEqual(len(self.lines), 28)
        self.assertEqual(self.lines[0].competencia, comp(2024, 4))
        self.assertEqual(self.lines[-1].competencia, comp(2026, 7))

    def test_todos_os_saldos_batem_com_a_planilha(self) -> None:
        for mes, line in enumerate(self.lines, start=1):
            with self.subTest(mes=mes, competencia=line.competencia):
                self.assertLessEqual(
                    abs(line.saldo_final - D(SALDO_PLANILHA[mes])),
                    TOLERANCIA_PLANILHA,
                    f"mês {mes}: motor {line.saldo_final} × planilha {SALDO_PLANILHA[mes]}",
                )

    def test_primeira_parcela_separa_juros_de_amortizacao(self) -> None:
        # R$ 15.500 pagos = R$ 3.000 de juros do mês + R$ 12.500 de amortização (100.000 ÷ 8).
        l1 = self.lines[0]
        self.assertEqual(l1.saldo_inicial, D("100000.00"))
        self.assertEqual(l1.encargo, D("3000.00"))
        self.assertEqual(l1.juros_pagos, D("3000.00"))
        self.assertEqual(l1.amortizacao, D("12500.00"))
        self.assertEqual(l1.saldo_final, D("87500.00"))

    def test_mes_sem_pagamento_capitaliza_o_encargo(self) -> None:
        # Set/2024: ninguém pagou, então o juro virou saldo — 37.500 → 38.625.
        set24 = self.lines[5]
        self.assertEqual(set24.competencia, comp(2024, 9))
        self.assertEqual(set24.pagamento, D("0.00"))
        self.assertEqual(set24.encargo, D("1125.00"))
        self.assertEqual(set24.saldo_final, D("38625.00"))
        # E no mês seguinte o juro incide sobre o saldo já capitalizado.
        self.assertEqual(self.lines[6].saldo_inicial, D("38625.00"))
        self.assertEqual(self.lines[6].encargo, D("1158.75"))

    def test_aporte_nao_rende_no_mes_em_que_entra(self) -> None:
        # Jan/2025: aporte de R$ 28.000 sobre saldo de R$ 42.206,58.
        # O juro do mês é 3% de 42.206,58 (1.266,20) — NÃO de 70.206,58 (2.106,20).
        jan25 = self.lines[9]
        self.assertEqual(jan25.competencia, comp(2025, 1))
        self.assertEqual(jan25.aporte, D("28000.00"))
        self.assertEqual(jan25.saldo_inicial, D("42206.58"))
        self.assertEqual(jan25.encargo, D("1266.20"))
        self.assertEqual(jan25.saldo_final, D("71472.78"))

    def test_pagamento_avulso_quita_juros_do_mes_e_amortiza_o_resto(self) -> None:
        # Nov/2025: R$ 100.000 = R$ 4.707,29 de juros do mês + R$ 95.292,71 de amortização.
        nov25 = self.lines[19]
        self.assertEqual(nov25.competencia, comp(2025, 11))
        self.assertEqual(nov25.pagamento, D("100000.00"))
        self.assertEqual(nov25.encargo, D("4707.29"))
        self.assertEqual(nov25.juros_pagos, D("4707.29"))
        self.assertEqual(nov25.amortizacao, D("95292.71"))

    def test_mudanca_de_taxa_vale_a_partir_da_competencia(self) -> None:
        self.assertEqual(self.lines[20].competencia, comp(2025, 12))
        self.assertEqual(self.lines[20].taxa, D("0.030000"))
        self.assertEqual(self.lines[21].competencia, comp(2026, 1))
        self.assertEqual(self.lines[21].taxa, D("0.015000"))
        self.assertEqual(self.lines[21].encargo, D("951.98"))

    def test_indicadores_consolidados(self) -> None:
        i = self.ind
        self.assertEqual(i.principal, D("100000.00"))
        self.assertEqual(i.total_aportes, D("88000.00"))
        self.assertEqual(i.total_contratado, D("188000.00"))
        self.assertEqual(i.total_pago, D("173750.00"))
        self.assertEqual(i.total_encargos, D("56186.95"))
        # A parte do encargo que virou caixa × a que virou mais dívida.
        self.assertEqual(i.encargos_pagos, D("15957.29"))
        self.assertEqual(i.encargos_capitalizados, D("40229.66"))
        self.assertEqual(i.total_amortizado, D("157792.71"))
        self.assertEqual(i.taxa_vigente, D("0.015000"))
        self.assertEqual(i.competencia_final, comp(2026, 7))

    def test_encargo_acumulado_fecha_com_a_soma_das_linhas(self) -> None:
        self.assertEqual(self.lines[-1].encargo_acumulado, self.ind.total_encargos)

    def test_pago_fecha_com_juros_mais_amortizacao(self) -> None:
        # Todo real pago é juro ou principal — não existe terceira gaveta.
        self.assertEqual(self.ind.encargos_pagos + self.ind.total_amortizado, self.ind.total_pago)

    def test_projecao_de_saldo_para_setembro(self) -> None:
        # A planilha para em 07/2026. Estendendo sem pagamento, o saldo em 09/2026.
        lines = build_ledger(through=comp(2026, 9), realized_through=comp(2026, 7), **PLANILHA)
        self.assertEqual(len(lines), 30)
        self.assertFalse(lines[27].is_projected)
        self.assertTrue(lines[28].is_projected)
        self.assertEqual(lines[28].encargo, D("1056.55"))
        self.assertEqual(lines[28].saldo_final, D("71493.50"))
        self.assertEqual(lines[29].saldo_final, D("72565.90"))


# --------------------------------------------------------------------------- #
# Regras isoladas                                                             #
# --------------------------------------------------------------------------- #


class TaxaVigenteTests(unittest.TestCase):
    def test_sem_vigencia_a_divida_fica_congelada(self) -> None:
        self.assertEqual(rate_for(comp(2026, 5), []), D("0.00"))

    def test_vale_a_maior_vigencia_menor_ou_igual(self) -> None:
        rates = [
            RateChange(valid_from=comp(2026, 1), monthly_rate=D("0.015")),
            RateChange(valid_from=comp(2024, 4), monthly_rate=D("0.03")),
        ]
        self.assertEqual(rate_for(comp(2024, 3), rates), D("0.00"))  # antes de tudo
        self.assertEqual(rate_for(comp(2024, 4), rates), D("0.030000"))
        self.assertEqual(rate_for(comp(2025, 12), rates), D("0.030000"))
        self.assertEqual(rate_for(comp(2026, 1), rates), D("0.015000"))
        self.assertEqual(rate_for(comp(2030, 1), rates), D("0.015000"))

    def test_duas_vigencias_no_mesmo_mes_sao_recusadas(self) -> None:
        rates = [
            RateChange(valid_from=comp(2026, 1), monthly_rate=D("0.01")),
            RateChange(valid_from=date(2026, 1, 20), monthly_rate=D("0.02")),
        ]
        with self.assertRaises(ValueError):
            rate_for(comp(2026, 1), rates)


class RegrasDoMotorTests(unittest.TestCase):
    def test_taxa_zero_congela_a_divida(self) -> None:
        lines = build_ledger(
            principal=D("50000.00"), origin_month=comp(2026, 1), through=comp(2026, 12)
        )
        self.assertEqual(len(lines), 12)
        self.assertTrue(all(ln.encargo == D("0.00") for ln in lines))
        self.assertEqual(lines[-1].saldo_final, D("50000.00"))

    def test_congelado_e_taxa_zero_dao_o_mesmo_numero(self) -> None:
        # É o que garante que ligar o motor numa dívida existente não muda valor nenhum.
        kwargs = dict(
            principal=D("50000.00"),
            origin_month=comp(2026, 1),
            through=comp(2026, 6),
            payments={comp(2026, 3): D("10000.00")},
        )
        sem_taxa = build_ledger(**kwargs)
        com_zero = build_ledger(rates=[RateChange(comp(2026, 1), D("0"))], **kwargs)
        self.assertEqual(
            [ln.saldo_final for ln in sem_taxa], [ln.saldo_final for ln in com_zero]
        )
        self.assertEqual(sem_taxa[-1].saldo_final, D("40000.00"))

    def test_pagamento_menor_que_o_juro_nao_amortiza_nada(self) -> None:
        # Juro de 1.000; paga 400 → nada de principal, e 600 capitalizam.
        lines = build_ledger(
            principal=D("100000.00"),
            origin_month=comp(2026, 1),
            through=comp(2026, 1),
            rates=[RateChange(comp(2026, 1), D("0.01"))],
            payments={comp(2026, 1): D("400.00")},
        )
        ln = lines[0]
        self.assertEqual(ln.encargo, D("1000.00"))
        self.assertEqual(ln.juros_pagos, D("400.00"))
        self.assertEqual(ln.amortizacao, D("0.00"))
        self.assertEqual(ln.saldo_final, D("100600.00"))

    def test_abatimento_reduz_saldo_sem_ser_pagamento(self) -> None:
        lines = build_ledger(
            principal=D("10000.00"),
            origin_month=comp(2026, 1),
            through=comp(2026, 1),
            events=[LedgerEvent(comp(2026, 1), ABATIMENTO, D("2500.00"))],
        )
        self.assertEqual(lines[0].saldo_final, D("7500.00"))
        self.assertEqual(compute_indicators(lines, principal=D("10000.00")).total_pago, D("0.00"))

    def test_encargo_manual_entra_no_contratado_e_nao_no_encargo_de_taxa(self) -> None:
        lines = build_ledger(
            principal=D("10000.00"),
            origin_month=comp(2026, 1),
            through=comp(2026, 1),
            events=[LedgerEvent(comp(2026, 1), ENCARGO_MANUAL, D("300.00"))],
        )
        ind = compute_indicators(lines, principal=D("10000.00"))
        self.assertEqual(lines[0].saldo_final, D("10300.00"))
        self.assertEqual(ind.total_encargos, D("0.00"))
        self.assertEqual(ind.total_contratado, D("10300.00"))

    def test_saldo_quitado_para_de_render(self) -> None:
        lines = build_ledger(
            principal=D("1000.00"),
            origin_month=comp(2026, 1),
            through=comp(2026, 3),
            rates=[RateChange(comp(2026, 1), D("0.10"))],
            payments={comp(2026, 1): D("1100.00")},
        )
        self.assertEqual(lines[0].saldo_final, D("0.00"))
        self.assertEqual(lines[1].encargo, D("0.00"))
        self.assertEqual(lines[2].saldo_final, D("0.00"))

    def test_varios_aportes_no_mesmo_mes_somam(self) -> None:
        lines = build_ledger(
            principal=D("1000.00"),
            origin_month=comp(2026, 1),
            through=comp(2026, 1),
            events=[
                LedgerEvent(comp(2026, 1), APORTE, D("500.00")),
                LedgerEvent(comp(2026, 1), APORTE, D("250.00")),
            ],
        )
        self.assertEqual(lines[0].aporte, D("750.00"))
        self.assertEqual(lines[0].saldo_final, D("1750.00"))

    def test_entradas_invalidas_sao_recusadas(self) -> None:
        base = dict(principal=D("100.00"), origin_month=comp(2026, 5))
        with self.assertRaises(ValueError):  # fim antes da origem
            build_ledger(through=comp(2026, 4), **base)
        with self.assertRaises(ValueError):  # tipo de evento inexistente
            build_ledger(
                through=comp(2026, 5),
                events=[LedgerEvent(comp(2026, 5), "DESCONTO", D("10"))],
                **base,
            )
        with self.assertRaises(ValueError):  # valor negativo (o sinal vem do tipo)
            build_ledger(
                through=comp(2026, 5),
                events=[LedgerEvent(comp(2026, 5), APORTE, D("-10"))],
                **base,
            )
        with self.assertRaises(ValueError):  # principal negativo
            build_ledger(principal=D("-1"), origin_month=comp(2026, 5), through=comp(2026, 5))

    def test_divida_sem_movimento_tem_indicadores_zerados(self) -> None:
        ind = compute_indicators([], principal=D("2500.00"))
        self.assertEqual(ind.saldo_atual, D("2500.00"))
        self.assertEqual(ind.total_encargos, D("0.00"))
        self.assertIsNone(ind.competencia_final)


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------- #
# Adaptador: de onde sai a competência de ORIGEM da dívida                     #
# --------------------------------------------------------------------------- #


class _Fake:
    """Objeto mínimo no formato do item — o adaptador só lê atributos."""

    def __init__(self, *, start_date=None, payments=(), events=(), created=date(2026, 5, 10)):
        self.start_date = start_date
        self.payments = [type("P", (), {"competencia": c})() for c in payments]
        self.events = [type("E", (), {"competencia": c})() for c in events]
        self.created_at = type("C", (), {"date": lambda _self: created})()


class OrigemDaDividaTests(unittest.TestCase):
    """Nada que o usuário lançou pode cair fora do razão — nem antes do início registrado."""

    def _origem(self, **kw):
        from app.services.debt_ledger_service import DebtLedgerService

        return DebtLedgerService.origin_month(_Fake(**kw))

    def test_usa_o_inicio_registrado(self) -> None:
        self.assertEqual(self._origem(start_date=date(2024, 4, 1)), comp(2024, 4))

    def test_sem_inicio_cai_no_primeiro_lancamento(self) -> None:
        self.assertEqual(self._origem(payments=[comp(2025, 3), comp(2025, 7)]), comp(2025, 3))

    def test_sem_nada_cai_no_mes_do_cadastro(self) -> None:
        self.assertEqual(self._origem(), comp(2026, 5))

    def test_evento_anterior_ao_inicio_puxa_a_origem(self) -> None:
        # O bug que isto trava: aporte em 03/2026 numa dívida que começava em 05/2026
        # simplesmente sumia do razão.
        self.assertEqual(
            self._origem(start_date=date(2026, 5, 1), events=[comp(2026, 3)]), comp(2026, 3)
        )

    def test_lancamento_anterior_ao_inicio_puxa_a_origem(self) -> None:
        self.assertEqual(
            self._origem(start_date=date(2026, 5, 1), payments=[comp(2024, 1)]), comp(2024, 1)
        )


class ProjecaoNaoContaminaOsTotaisTests(unittest.TestCase):
    """Linha projetada é hipótese: não pode virar encargo cobrado nem saldo de hoje.

    O bug que isto trava apareceu na tela: o cabeçalho mostrava "Saldo hoje R$ 19.055,28",
    que era o saldo do ÚLTIMO mês projetado (6 meses à frente), e os encargos já cobrados
    incluíam meses que ainda não tinham acontecido.
    """

    def setUp(self) -> None:
        # Dívida de 19.000 desde 08/2026, 0,5% a.m. desde 09/2026, realizada até 09/2026.
        self.lines = build_ledger(
            principal=D("19000.00"),
            origin_month=comp(2026, 8),
            through=comp(2027, 3),
            rates=[RateChange(comp(2026, 9), D("0.005"))],
            payments={comp(2026, 8): D("300.00"), comp(2026, 9): D("300.00")},
            realized_through=comp(2026, 9),
        )
        self.ind = compute_indicators(self.lines, principal=D("19000.00"))

    def test_saldo_atual_e_o_do_ultimo_mes_realizado(self) -> None:
        self.assertEqual(self.ind.saldo_atual, D("18493.50"))
        self.assertEqual(self.ind.competencia_final, comp(2026, 9))

    def test_projecao_sai_a_parte(self) -> None:
        self.assertEqual(self.ind.saldo_projetado, D("19055.28"))
        self.assertEqual(self.ind.competencia_projecao, comp(2027, 3))

    def test_encargo_cobrado_conta_so_o_que_ja_aconteceu(self) -> None:
        # Só 09/2026 teve encargo realizado: 18.700 × 0,5%.
        self.assertEqual(self.ind.total_encargos, D("93.50"))
        self.assertEqual(self.ind.encargos_pagos, D("93.50"))
        self.assertEqual(self.ind.encargos_capitalizados, D("0.00"))

    def test_pago_e_amortizado_ignoram_o_futuro(self) -> None:
        self.assertEqual(self.ind.total_pago, D("600.00"))
        self.assertEqual(self.ind.total_amortizado, D("506.50"))

    def test_sem_projecao_nada_muda(self) -> None:
        # Mesma dívida sem estender o horizonte: os totais têm que ser idênticos.
        sem_proj = compute_indicators(
            [ln for ln in self.lines if not ln.is_projected], principal=D("19000.00")
        )
        self.assertEqual(sem_proj.saldo_atual, self.ind.saldo_atual)
        self.assertEqual(sem_proj.total_encargos, self.ind.total_encargos)
        self.assertIsNone(sem_proj.saldo_projetado)

    def test_tudo_projetado_devolve_o_principal(self) -> None:
        # Caso de borda: razão sem nenhum mês realizado (dívida que começa no futuro).
        futuras = build_ledger(
            principal=D("1000.00"),
            origin_month=comp(2027, 1),
            through=comp(2027, 3),
            rates=[RateChange(comp(2027, 1), D("0.01"))],
            realized_through=comp(2026, 12),
        )
        ind = compute_indicators(futuras, principal=D("1000.00"))
        self.assertEqual(ind.saldo_atual, D("1000.00"))
        self.assertEqual(ind.total_encargos, D("0.00"))
        self.assertEqual(ind.saldo_projetado, D("1030.30"))


class TaxaPadraoQuandoNadaFoiDefinidoTests(unittest.TestCase):
    """Dívida sem taxa configurada corre no padrão do SGC — não fica parada no tempo.

    Decisão de produto: "se eu não mexer em nada, quero saber a evolução dessa dívida sempre
    calculando o juros mês a mês". Para CONGELAR, o usuário lança explicitamente 0%.
    """

    def _resolver(self, rates, padrao="0.005"):
        from app.services.debt_ledger_service import DebtLedgerService

        item = _Fake()
        item.rates = [
            type("R", (), {"valid_from": vf, "monthly_rate": mr})() for vf, mr in rates
        ]
        svc = DebtLedgerService.__new__(DebtLedgerService)  # sem sessão: o método é puro
        return svc._vigencias_com_padrao(item, comp(2026, 1), D(padrao))

    def test_sem_vigencia_herda_o_padrao(self) -> None:
        vigencias, usando_padrao = self._resolver([])
        self.assertTrue(usando_padrao)
        self.assertEqual(len(vigencias), 1)
        self.assertEqual(vigencias[0].monthly_rate, D("0.005000"))
        self.assertEqual(vigencias[0].valid_from, comp(2026, 1))

    def test_vigencia_propria_manda_no_padrao(self) -> None:
        vigencias, usando_padrao = self._resolver([(comp(2026, 3), D("0.02"))])
        self.assertFalse(usando_padrao)
        self.assertEqual([v.monthly_rate for v in vigencias], [D("0.020000")])

    def test_zero_explicito_congela_e_nao_volta_para_o_padrao(self) -> None:
        # A diferença entre "não configurei" e "quero congelada" é justamente esta.
        vigencias, usando_padrao = self._resolver([(comp(2026, 1), D("0"))])
        self.assertFalse(usando_padrao)
        self.assertEqual(rate_for(comp(2026, 6), vigencias), D("0.00"))

    def test_padrao_zero_no_sistema_mantem_tudo_congelado(self) -> None:
        vigencias, usando_padrao = self._resolver([], padrao="0")
        self.assertFalse(usando_padrao)
        self.assertEqual(vigencias, [])


class CampoAusenteNaoEhCampoNuloTests(unittest.TestCase):
    """Numa linha da planilha, NÃO mandar um campo é diferente de mandá-lo vazio.

    O bug que isto trava: o router serializava as linhas com `model_dump()` sem
    `exclude_unset`, então todo campo omitido virava `None` — e o serviço lê `pagamento=None`
    como "apague o lançamento deste mês". Resultado: o pagamento sumia dos meses que a tela
    reenviava por outro motivo (ter uma vigência de taxa), tanto no recálculo quanto ao salvar.
    """

    def _linha(self, **kwargs):
        from app.schemas.company_finance import DebtLedgerRowIn

        return DebtLedgerRowIn(competencia=comp(2024, 4), **kwargs)

    def test_campo_omitido_nao_aparece_no_dump(self) -> None:
        dump = self._linha(taxa=0.03).model_dump(exclude_unset=True)
        self.assertIn("taxa", dump)
        self.assertNotIn("pagamento", dump)
        self.assertNotIn("aporte", dump)

    def test_campo_explicitamente_nulo_aparece(self) -> None:
        # É assim que a tela diz "esvaziei esta caixa": o mês perde o lançamento.
        dump = self._linha(pagamento=None).model_dump(exclude_unset=True)
        self.assertIn("pagamento", dump)
        self.assertIsNone(dump["pagamento"])

    def test_sem_exclude_unset_o_dump_inventa_nulos(self) -> None:
        # Documenta a causa raiz: é este comportamento que o router precisa evitar.
        dump = self._linha(taxa=0.03).model_dump()
        self.assertIn("pagamento", dump)
        self.assertIsNone(dump["pagamento"])


class DividaQueComecaNoFuturoTests(unittest.TestCase):
    """Dívida cadastrada para começar depois de hoje não pode derrubar a tela.

    O razão vai da origem até hoje; quando a origem é POSTERIOR a hoje, o intervalo sai
    invertido. Antes da correção isso levantava "competência final é anterior à origem" e
    derrubava a listagem INTEIRA do Endividamento — não só o item com a data no futuro.
    """

    def test_intervalo_invertido_e_recusado_pelo_nucleo(self) -> None:
        # O núcleo continua rígido de propósito: quem chama é que precisa ordenar o intervalo.
        with self.assertRaises(ValueError):
            build_ledger(principal=D("100"), origin_month=comp(2099, 8), through=comp(2026, 9))

    def test_uma_competencia_quando_origem_e_fim_coincidem(self) -> None:
        linhas = build_ledger(
            principal=D("100.00"), origin_month=comp(2099, 8), through=comp(2099, 8)
        )
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0].saldo_final, D("100.00"))


class PlanejadorDeParcelasTests(unittest.TestCase):
    """Quanto pagar por mês quando o juro CONTINUA correndo.

    A pergunta que o cronograma de parcelas fixas não responde: com encargo incidindo, fixar a
    parcela e fixar a amortização dão planos diferentes. Os números conferidos aqui são os do
    saldo real de uma dívida (R$ 72.565,90 a 1,5% a.m.).
    """

    SALDO = D("72565.90")
    RATES = [RateChange(comp(2026, 10), D("0.015"))]

    def _plano(self, mode, **kw):
        from app.services.debt_accrual import plan_installments

        return plan_installments(
            saldo=self.SALDO, start_month=comp(2026, 10), rates=self.RATES, mode=mode, **kw
        )

    def test_amortizacao_fixa_faz_a_parcela_cair(self) -> None:
        # O desenho do acordo original da planilha: abate 10.000 de principal e paga o juro.
        from app.services.debt_accrual import MODE_AMORT_FIXA

        p = self._plano(MODE_AMORT_FIXA, amount=D("10000"))
        self.assertEqual(p.count, 8)
        self.assertEqual(p.parcelas[0].valor, D("11088.49"))
        self.assertEqual(p.parcelas[0].amortizacao, D("10000.00"))
        self.assertEqual(p.parcelas[1].valor, D("10938.49"))  # cai, porque o saldo caiu
        self.assertEqual(p.parcelas[-1].saldo_final, D("0.00"))
        self.assertEqual(p.total_juros, D("4507.92"))

    def test_parcela_fixa_mantem_o_valor_e_muda_a_amortizacao(self) -> None:
        from app.services.debt_accrual import MODE_PARCELA_FIXA

        p = self._plano(MODE_PARCELA_FIXA, amount=D("10000"))
        self.assertTrue(all(x.valor == D("10000.00") for x in p.parcelas[:-1]))
        self.assertLess(p.parcelas[0].amortizacao, p.parcelas[1].amortizacao)
        self.assertEqual(p.parcelas[-1].saldo_final, D("0.00"))
        self.assertEqual(p.total_juros, D("4850.67"))

    def test_quitar_em_n_parcelas_fecha_exatamente_em_n(self) -> None:
        # O resíduo de arredondamento entra na última parcela — nunca cria uma parcela a mais.
        from app.services.debt_accrual import MODE_N_PARCELAS

        p = self._plano(MODE_N_PARCELAS, count=12)
        self.assertEqual(p.count, 12)
        self.assertEqual(p.parcelas[0].valor, D("6652.84"))
        self.assertEqual(p.parcelas[-1].saldo_final, D("0.00"))

    def test_parcela_que_nao_cobre_o_juro_e_recusada(self) -> None:
        # 1,5% de 72.565,90 = 1.088,49: pagar 500 por mês nunca quitaria.
        from app.services.debt_accrual import MODE_PARCELA_FIXA

        with self.assertRaises(ValueError):
            self._plano(MODE_PARCELA_FIXA, amount=D("500"))

    def test_mudanca_de_taxa_no_meio_do_plano_e_respeitada(self) -> None:
        from app.services.debt_accrual import MODE_AMORT_FIXA, plan_installments

        p = plan_installments(
            saldo=D("30000"),
            start_month=comp(2026, 10),
            rates=[RateChange(comp(2026, 10), D("0.03")), RateChange(comp(2026, 12), D("0"))],
            mode=MODE_AMORT_FIXA,
            amount=D("10000"),
        )
        self.assertEqual(p.parcelas[0].juros, D("900.00"))  # 3% de 30.000
        self.assertEqual(p.parcelas[2].juros, D("0.00"))  # taxa zerou em 12/2026
        self.assertEqual(p.count, 3)

    def test_sem_juros_o_plano_e_a_divisao_simples(self) -> None:
        from app.services.debt_accrual import MODE_N_PARCELAS, plan_installments

        p = plan_installments(
            saldo=D("12000"), start_month=comp(2026, 10), rates=[], mode=MODE_N_PARCELAS, count=12
        )
        self.assertEqual(p.count, 12)
        self.assertTrue(all(x.valor == D("1000.00") for x in p.parcelas))
        self.assertEqual(p.total_juros, D("0.00"))
