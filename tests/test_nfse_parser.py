"""Regressão: leitura da NFS-e de São Paulo para pré-preencher o cadastro de NF.

Os números usados aqui vieram de notas reais do contrato 4600003861 (Treinamento
Enel SP). O líquido calculado pela fórmula do contador (bruto − 6,15%) foi conferido
contra o "Valor líquido a receber" escrito nas próprias notas.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.nfse_parser import (
    NET_FACTOR,
    NfseParseError,
    compute_net_amount,
    parse_nfse_pdf,
    parse_nfse_text,
)

# Recorte do texto extraído de uma NFS-e real (NF 3424), preservando o layout em colunas.
NFSE_TEXT = """
                                                              Número da Nota
     PREFEITURA DO MUNICÍPIO DE SÃO PAULO                            00003424
              SECRETARIA MUNICIPAL DA FAZENDA                 Data e Hora de Emissão
                                                               04/08/2026 17:56:47
       NOTA FISCAL ELETRÔNICA DE SERVIÇOS - NFS-e             Código de Verificação
20260804u08152526000107                                             KMDW-CAA9

                              PRESTADOR DE SERVIÇOS
     CPF/CNPJ: 08.152.526/0001-07                Inscrição Municipal: 3.538.583-9
     Nome/Razão Social: M&E ENGENHARIA, SERVICOS E CONSTRUCOES S A

                               TOMADOR DE SERVIÇOS
Nome/Razão Social: ELETROPAULO METROPOLITANA ELETRICIDADE DE SAO PAULO S/A
CPF/CNPJ: 61.695.227/0002-74                     Inscrição Municipal: 1.236.383-9

                            DISCRIMINAÇÃO DE SERVIÇOS
Treinamentos Normativos – Enel SP
Contrato nº 4600003861
Julho – 2026

Valor líquido a receber: R$ 75.264,74

                      VALOR TOTAL DO SERVIÇO = R$ 80.196,85
"""


def test_extrai_todos_os_campos_do_cadastro() -> None:
    p = parse_nfse_text(NFSE_TEXT)
    assert p.nf_number == "3424"  # zeros à esquerda descartados
    assert p.issue_date == date(2026, 8, 4)
    assert p.competence_month == date(2026, 7, 1)  # "Julho – 2026" → 1º do mês
    assert p.gross_amount == Decimal("80196.85")
    assert p.client_name == "ELETROPAULO METROPOLITANA ELETRICIDADE DE SAO PAULO S/A"
    assert p.client_document == "61.695.227/0002-74"
    assert p.contract_number == "4600003861"
    assert p.description == "Treinamentos Normativos – Enel SP"
    assert p.warnings == []


def test_cliente_e_o_tomador_nao_o_prestador() -> None:
    """O bloco do prestador (M&E) vem antes no PDF e não pode virar o cliente."""
    p = parse_nfse_text(NFSE_TEXT)
    assert p.client_name is not None
    assert "M&E" not in p.client_name
    assert p.client_document != "08.152.526/0001-07"


@pytest.mark.parametrize(
    "gross,expected_net",
    [
        # Notas reais: o líquido calculado bate com o declarado na discriminação.
        ("61534.58", "57750.20"),
        ("73912.08", "69366.49"),
        ("88937.90", "83468.22"),
        ("63743.98", "59823.73"),
        ("80196.85", "75264.74"),
        # Exemplo da planilha do contador.
        ("120506.43", "113095.28"),
    ],
)
def test_liquido_segue_a_formula_do_contador(gross: str, expected_net: str) -> None:
    assert compute_net_amount(Decimal(gross)) == Decimal(expected_net)


def test_fator_liquido_e_bruto_menos_6_15_porcento() -> None:
    """IRRF 1,5% + PIS 0,65% + COFINS 3% + CSLL 1% = 6,15% de retenção."""
    assert NET_FACTOR == Decimal("0.9385")


def test_liquido_e_calculado_mesmo_sem_estar_escrito_na_nota() -> None:
    """A maioria das notas não traz o líquido; ele não pode depender disso."""
    sem_liquido = NFSE_TEXT.replace("Valor líquido a receber: R$ 75.264,74", "")
    p = parse_nfse_text(sem_liquido)
    assert p.declared_net_amount is None
    assert p.net_amount == Decimal("75264.74")
    assert p.warnings == []


def test_avisa_quando_o_liquido_escrito_diverge_do_calculado() -> None:
    divergente = NFSE_TEXT.replace("75.264,74", "70.000,00")
    p = parse_nfse_text(divergente)
    assert p.declared_net_amount == Decimal("70000.00")
    assert p.net_amount == Decimal("75264.74")  # a fórmula prevalece
    assert any("difere" in w for w in p.warnings)


def test_aceita_liquido_sem_dois_pontos() -> None:
    """Algumas notas escrevem "Valor líquido a receber R$ ..." sem os dois pontos."""
    p = parse_nfse_text(NFSE_TEXT.replace("a receber:", "a receber"))
    assert p.declared_net_amount == Decimal("75264.74")


@pytest.mark.parametrize("dash", ["-", "–", "—"])
def test_competencia_aceita_variacoes_de_traco(dash: str) -> None:
    p = parse_nfse_text(NFSE_TEXT.replace("Julho – 2026", f"Julho {dash} 2026"))
    assert p.competence_month == date(2026, 7, 1)


def _pdf_sem_texto() -> bytes:
    """PDF válido, porém só com desenho — como as NFs antigas, que são captura de tela."""
    from io import BytesIO

    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.rect(50, 50, 400, 600, fill=0)
    c.showPage()
    c.save()
    return buf.getvalue()


def test_pdf_sem_camada_de_texto_e_recusado_com_mensagem_clara() -> None:
    """NFs antigas são captura de tela: não dá para extrair, e o usuário precisa saber."""
    with pytest.raises(NfseParseError) as exc:
        parse_nfse_pdf(_pdf_sem_texto())
    assert "manualmente" in str(exc.value)
