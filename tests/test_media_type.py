"""Mime servido para os anexos — é o que decide se o botão "Ver" exibe ou baixa o arquivo."""

from __future__ import annotations

import unittest

from app.utils.media_type import FALLBACK, resolve_media_type


class ResolveMediaTypeTests(unittest.TestCase):
    def test_mime_especifico_do_upload_vence(self) -> None:
        self.assertEqual(resolve_media_type("application/pdf", "nota.pdf"), "application/pdf")
        self.assertEqual(resolve_media_type("image/jpeg", "recibo.bin"), "image/jpeg")

    def test_generico_ou_vazio_cai_para_a_extensao(self) -> None:
        # O caso real: upload sem Content-Type (ou octet-stream) faria o navegador baixar.
        self.assertEqual(resolve_media_type(None, "comprovante.pdf"), "application/pdf")
        self.assertEqual(resolve_media_type("", "comprovante.pdf"), "application/pdf")
        self.assertEqual(
            resolve_media_type("application/octet-stream", "foto.png"), "image/png"
        )

    def test_formatos_de_foto_que_o_sistema_nao_conhece(self) -> None:
        self.assertEqual(resolve_media_type(None, "IMG_0042.HEIC"), "image/heic")
        self.assertEqual(resolve_media_type(None, "recibo.webp"), "image/webp")

    def test_sem_pista_alguma_fica_no_generico(self) -> None:
        self.assertEqual(resolve_media_type(None, "arquivo_sem_extensao"), FALLBACK)
        self.assertEqual(resolve_media_type(None, None), FALLBACK)


if __name__ == "__main__":
    unittest.main()
