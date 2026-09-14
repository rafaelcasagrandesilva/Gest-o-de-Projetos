"""Devolve ao sistema operacional a memória que o Python já liberou.

O Python não devolve ao SO tudo o que libera: guarda o espaço para reaproveitar no próximo
uso. Isso é ótimo para desempenho e ruim para a fatura do Railway, que cobra **MB × minuto** —
memória reservada e ociosa custa igual a memória em uso. Uma exportação de relatório que sobe
o consumo em 100 MB deixa esses 100 MB reservados até o processo reiniciar, e eles são
cobrados a cada minuto até lá (~US$ 0,03 por dia a cada 100 MB).

`malloc_trim` é a chamada do glibc que devolve as páginas já livres. Ela **não muda
comportamento nenhum**: só entrega de volta o que o Python já considera lixo. Nada de dado
vivo é tocado.

Recupera parte, não tudo: objetos pequenos vivem nas arenas do pymalloc, que só voltam ao SO
quando a arena inteira esvazia, e a fragmentação frequentemente impede isso. Na prática
sobra uma fração retida — o ganho é real, mas parcial.

Fora do glibc (macOS, Alpine/musl) a função não existe e tudo aqui vira no-op silencioso: o
ambiente de desenvolvimento não precisa disso, e produção roda em Debian/glibc.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging

logger = logging.getLogger(__name__)

#: `None` = ainda não tentamos carregar; `False` = indisponível neste sistema.
_malloc_trim: object | None = None


def _resolver_malloc_trim():
    """Localiza `malloc_trim` uma única vez e guarda o resultado (inclusive a ausência)."""
    global _malloc_trim
    if _malloc_trim is not None:
        return _malloc_trim or None

    try:
        # `find_library` cobre as variações de nome entre distribuições; o fallback direto
        # atende as imagens onde ele não encontra nada mas a libc está carregada.
        nome = ctypes.util.find_library("c") or "libc.so.6"
        libc = ctypes.CDLL(nome)
        funcao = libc.malloc_trim
        funcao.argtypes = [ctypes.c_size_t]
        funcao.restype = ctypes.c_int
    except (OSError, AttributeError):
        _malloc_trim = False
        logger.info("malloc_trim indisponível neste sistema; devolução de memória desativada.")
        return None

    _malloc_trim = funcao
    return funcao


def memory_trim_available() -> bool:
    """Se a devolução de memória funciona neste sistema (glibc)."""
    return _resolver_malloc_trim() is not None


def current_rss_bytes() -> int | None:
    """Memória residente do processo, lida de /proc. `None` fora do Linux.

    É esta a métrica que o Railway cobra — o que o processo segura, não o que ele usa de
    fato.
    """
    try:
        with open("/proc/self/statm", "rb") as arquivo:
            paginas = int(arquivo.read().split()[1])
    except (OSError, IndexError, ValueError):
        return None
    # statm conta em páginas; 4 KiB é o tamanho em toda arquitetura que usamos.
    return paginas * 4096


def release_free_memory() -> bool:
    """Pede ao glibc que devolva as páginas livres. `True` se a chamada aconteceu.

    Seguro para chamar sempre: quando não há nada a devolver, é uma varredura barata das
    listas de livres e o retorno é `False` do próprio glibc (aqui reportado como `True`,
    porque o que interessa ao chamador é se a tentativa ocorreu).
    """
    funcao = _resolver_malloc_trim()
    if funcao is None:
        return False
    try:
        funcao(0)
    except OSError:
        return False
    return True
