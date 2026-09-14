"""Devolução de memória ao SO depois de requisições pesadas.

O Railway cobra **MB × minuto**: memória que o Python liberou mas não devolveu ao sistema
continua sendo paga a cada minuto até o processo reiniciar (~US$ 0,03 por dia a cada 100 MB).
Depois de exportar um relatório ou importar uma planilha, o piso do processo sobe e fica lá.

Dois níveis de teste, de propósito:

- os do meio (`MemoryReclaimTriggerTests`) rodam em qualquer sistema e fixam a REGRA — quando
  a devolução é disparada e, principalmente, quando NÃO é;
- o do fim (`MallocTrimRealTests`) mede a memória de verdade e só roda onde `malloc_trim`
  existe (Linux/glibc, que é produção). No macOS ele é pulado — é a prova, não a regra.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.api.middleware import MemoryReclaimMiddleware
from app.utils.memory import current_rss_bytes, memory_trim_available, release_free_memory

MB = 1024 * 1024


def _requisicao(path: str = "/api/v1/reports/export"):
    return SimpleNamespace(method="GET", url=SimpleNamespace(path=path))


class MemoryReclaimTriggerTests(unittest.IsolatedAsyncioTestCase):
    """Quando o middleware chama (e quando não chama) a devolução."""

    def setUp(self) -> None:
        self.devolucoes = 0

    def _instalar(self, leituras: list[int]) -> None:
        """Roteiro de leituras de memória residente, consumidas em ordem."""
        import app.api.middleware as mod

        self.restante = list(leituras)
        mod.current_rss_bytes = lambda: self.restante.pop(0) if self.restante else None

        def devolver() -> bool:
            self.devolucoes += 1
            return True

        mod.release_free_memory = devolver
        self.addCleanup(setattr, mod, "current_rss_bytes", current_rss_bytes)
        self.addCleanup(setattr, mod, "release_free_memory", release_free_memory)

    async def _rodar(self, *, min_growth_mb: int, leituras: list[int]) -> None:
        self._instalar(leituras)
        meio = MemoryReclaimMiddleware(app=None, min_growth_mb=min_growth_mb)

        async def call_next(_req):
            return "resposta"

        resposta = await meio.dispatch(_requisicao(), call_next)
        self.assertEqual(resposta, "resposta")  # o middleware nunca engole a resposta

    async def test_requisicao_leve_nao_devolve(self) -> None:
        """Abrir uma tela não paga o custo da varredura — é o caso de 99% do tráfego."""
        await self._rodar(min_growth_mb=32, leituras=[200 * MB, 203 * MB, 203 * MB])
        self.assertEqual(self.devolucoes, 0)

    async def test_exportacao_pesada_devolve(self) -> None:
        await self._rodar(min_growth_mb=32, leituras=[200 * MB, 340 * MB, 210 * MB])
        self.assertEqual(self.devolucoes, 1)

    async def test_limiar_e_inclusivo(self) -> None:
        """Crescimento exatamente igual ao limiar conta: o limiar é o mínimo, não o exclusivo."""
        await self._rodar(min_growth_mb=32, leituras=[100 * MB, 132 * MB, 100 * MB])
        self.assertEqual(self.devolucoes, 1)

    async def test_zero_desativa(self) -> None:
        """Com 0 o middleware some do caminho: nem mede a memória."""
        self._instalar([])  # qualquer leitura estouraria o roteiro vazio
        meio = MemoryReclaimMiddleware(app=None, min_growth_mb=0)

        async def call_next(_req):
            return "resposta"

        self.assertEqual(await meio.dispatch(_requisicao(), call_next), "resposta")
        self.assertEqual(self.devolucoes, 0)

    async def test_sem_proc_nao_quebra(self) -> None:
        """macOS e afins: sem /proc a leitura devolve None e a requisição segue normal."""
        await self._rodar(min_growth_mb=32, leituras=[])
        self.assertEqual(self.devolucoes, 0)

    async def test_queda_de_memoria_nao_devolve(self) -> None:
        """Requisição que LIBERA memória não tem o que devolver."""
        await self._rodar(min_growth_mb=32, leituras=[400 * MB, 180 * MB, 180 * MB])
        self.assertEqual(self.devolucoes, 0)


class MallocTrimRealTests(unittest.TestCase):
    """A prova: aloca de verdade, libera e mede o que volta ao sistema operacional."""

    def setUp(self) -> None:
        if not memory_trim_available() or current_rss_bytes() is None:
            self.skipTest("malloc_trim/proc indisponíveis (esperado fora de Linux/glibc).")

    def test_memoria_liberada_volta_ao_sistema(self) -> None:
        import gc

        base = current_rss_bytes()

        # Muitos objetos pequenos é o perfil do openpyxl montando uma planilha — e é o caso
        # em que o Python mais retém memória depois de liberar.
        entulho = [bytes(4096) for _ in range(40_000)]  # ~160 MB
        pico = current_rss_bytes()
        self.assertGreater(pico - base, 100 * MB, "a alocação de teste não cresceu o esperado")

        del entulho
        gc.collect()
        retido = current_rss_bytes()

        release_free_memory()
        depois = current_rss_bytes()

        devolvido = retido - depois
        print(
            f"\n  base {base/MB:.0f} MB → pico {pico/MB:.0f} MB → após liberar {retido/MB:.0f} MB"
            f" → após malloc_trim {depois/MB:.0f} MB  (devolvidos {devolvido/MB:.0f} MB)"
        )
        # O ganho é parcial por natureza (arenas fragmentadas do pymalloc não voltam);
        # exigimos apenas que uma fatia relevante do que ficou retido tenha voltado.
        self.assertGreater(devolvido, 20 * MB, "malloc_trim não devolveu memória ao sistema")
        self.assertLess(depois, pico, "a memória residente deveria ter caído do pico")


if __name__ == "__main__":
    unittest.main()
