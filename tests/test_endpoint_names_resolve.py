"""Nenhum endpoint pode referenciar um nome que não existe no seu escopo.

Nasceu de um bug real: `create_manual_payables_snapshot` chamava
`redact_for(..., user)` sem ter `user` entre os parâmetros. O handler só quebrava
quando alguém salvava uma despesa avulsa — e, pior, DEPOIS do `commit`: a despesa
era gravada e o navegador mostrava só "Network Error", porque um 500 não passa
pelo middleware de CORS e o front nunca vê o status real.

`NameError` é invisível para o type-checker do Python e para os testes que não
exercitam aquela rota. Esta varredura estática cobre TODOS os handlers de uma vez.
"""

from __future__ import annotations

import ast
import builtins
import pathlib
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent / "app"


def _nomes_do_modulo(tree: ast.Module) -> set[str]:
    """Tudo que é visível no escopo global do módulo (inclui `X: T = ...` e imports em try/if)."""
    nomes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            nomes |= {(a.asname or a.name).split(".")[0] for a in node.names}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            nomes |= {t.id for t in ast.walk(node) if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            nomes.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nomes.add(node.name)
        elif isinstance(node, (ast.If, ast.Try)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    nomes |= {t.id for t in ast.walk(sub) if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store)}
    return nomes


def _corpo_proprio(fn: ast.AST):
    """Nós da função, SEM entrar em funções aninhadas (cada uma é verificada no seu próprio passe)."""
    pilha = list(ast.iter_child_nodes(fn))
    while pilha:
        node = pilha.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        pilha += list(ast.iter_child_nodes(node))


def _nomes_da_funcao(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Parâmetros + tudo que a função liga no próprio corpo (inclui alvos de for/with/except)."""
    args = fn.args
    nomes = {a.arg for a in args.args + args.posonlyargs + args.kwonlyargs}
    if args.vararg:
        nomes.add(args.vararg.arg)
    if args.kwarg:
        nomes.add(args.kwarg.arg)
    for node in _corpo_proprio(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            nomes.add(node.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            nomes.add(node.target.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            nomes.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nomes.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            nomes |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, ast.Lambda):
            nomes |= {a.arg for a in node.args.args}
    return nomes


def _indefinidos(arquivo: pathlib.Path) -> list[str]:
    tree = ast.parse(arquivo.read_text(encoding="utf-8"))
    globais = _nomes_do_modulo(tree) | set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
    achados: list[str] = []

    def visita(node: ast.AST, herdado: set[str]) -> None:
        """`herdado` carrega o escopo das funções externas (closures)."""
        for filho in ast.iter_child_nodes(node):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)):
                meu = _nomes_da_funcao(filho)
                conhecidos = meu | herdado | globais
                for n in _corpo_proprio(filho):
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in conhecidos:
                        achados.append(
                            f"{arquivo.relative_to(RAIZ.parent)}:{n.lineno} "
                            f"{filho.name}() usa '{n.id}', que não existe no escopo"
                        )
                visita(filho, conhecidos)
            else:
                visita(filho, herdado)

    visita(tree, set())
    return achados


class EndpointNamesResolveTests(unittest.TestCase):
    def test_handlers_nao_usam_nome_inexistente(self):
        """O caso original: `redact_for(..., user)` sem `user` na assinatura do endpoint."""
        problemas: list[str] = []
        for arquivo in sorted(RAIZ.glob("modules/**/router.py")):
            problemas += _indefinidos(arquivo)
        self.assertEqual(problemas, [], "\n" + "\n".join(problemas))

    def test_endpoint_que_redige_valores_recebe_o_usuario(self):
        """`redact_for`/`sensitive_include` decidem por USUÁRIO — sem ele, ou quebra ou vaza."""
        faltando: list[str] = []
        for arquivo in sorted(RAIZ.glob("modules/**/router.py")):
            tree = ast.parse(arquivo.read_text(encoding="utf-8"))
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not any(
                    isinstance(n, ast.Call) and getattr(n.func, "id", "") in {"redact_for", "sensitive_include"}
                    for n in ast.walk(fn)
                ):
                    continue
                escopo = _nomes_da_funcao(fn)
                usados = {n.id for n in _corpo_proprio(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
                # Funções aninhadas herdam o usuário do handler externo — só o topo é cobrado.
                aninhada = any(
                    isinstance(pai, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn in ast.walk(pai) and pai is not fn
                    for pai in ast.walk(tree)
                    if isinstance(pai, (ast.FunctionDef, ast.AsyncFunctionDef))
                )
                if aninhada:
                    continue
                for ator in ("user", "actor", "current_user"):
                    if ator in usados and ator not in escopo:
                        faltando.append(
                            f"{arquivo.relative_to(RAIZ.parent)}:{fn.lineno} {fn.name}() "
                            f"redige valores com '{ator}', mas não o recebe por dependência"
                        )
        self.assertEqual(faltando, [], "\n" + "\n".join(faltando))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
