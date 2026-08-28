"""Regressão: todo upload em disco precisa nascer na mesma raiz das NFs.

Bug de origem: em produção só RECEIVABLE_UPLOAD_DIR apontava para o volume
persistente. Anexos de ativos e documentos de projeto ficavam no default relativo
(container efêmero) e sumiam no redeploy — o registro continuava no banco e o
download devolvia 404.

Não toca no banco (só configuração e disco em tmp_path).
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings

STORAGE_VARS = ("STORAGE_ROOT", "RECEIVABLE_UPLOAD_DIR", "ASSET_UPLOAD_DIR", "PROJECT_DOCUMENT_DIR")


def _settings(monkeypatch, **env: str) -> Settings:
    for var in STORAGE_VARS:
        monkeypatch.delenv(var, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_sem_variaveis_mantem_defaults_relativos(monkeypatch) -> None:
    dirs = _settings(monkeypatch).storage_dirs()
    assert dirs["RECEIVABLE_UPLOAD_DIR"] == Path("var/receivable_uploads")
    assert dirs["ASSET_UPLOAD_DIR"] == Path("var/asset_uploads")
    assert dirs["PROJECT_DOCUMENT_DIR"] == Path("var/project_documents")


def test_storage_root_governa_os_tres_diretorios(monkeypatch) -> None:
    dirs = _settings(monkeypatch, STORAGE_ROOT="/data").storage_dirs()
    assert dirs["RECEIVABLE_UPLOAD_DIR"] == Path("/data/receivable_uploads")
    assert dirs["ASSET_UPLOAD_DIR"] == Path("/data/asset_uploads")
    assert dirs["PROJECT_DOCUMENT_DIR"] == Path("/data/project_documents")


def test_deriva_do_diretorio_das_nfs_quando_so_ele_esta_definido(monkeypatch) -> None:
    """Cenário de produção hoje: só a var das NFs aponta para o volume."""
    dirs = _settings(monkeypatch, RECEIVABLE_UPLOAD_DIR="/data/receivable_uploads").storage_dirs()
    assert dirs["ASSET_UPLOAD_DIR"] == Path("/data/asset_uploads")
    assert dirs["PROJECT_DOCUMENT_DIR"] == Path("/data/project_documents")


def test_nf_apontando_para_a_raiz_do_volume_nao_vira_barra(monkeypatch) -> None:
    dirs = _settings(monkeypatch, RECEIVABLE_UPLOAD_DIR="/data").storage_dirs()
    assert dirs["RECEIVABLE_UPLOAD_DIR"] == Path("/data")
    assert dirs["PROJECT_DOCUMENT_DIR"] == Path("/data/project_documents")


def test_variavel_explicita_vence_a_raiz(monkeypatch) -> None:
    dirs = _settings(monkeypatch, STORAGE_ROOT="/data", PROJECT_DOCUMENT_DIR="/outro/docs").storage_dirs()
    assert dirs["PROJECT_DOCUMENT_DIR"] == Path("/outro/docs")
    assert dirs["ASSET_UPLOAD_DIR"] == Path("/data/asset_uploads")


def test_salvage_copia_do_legado_e_e_idempotente(monkeypatch, tmp_path) -> None:
    from app.utils import storage

    legado = tmp_path / "legado"
    (legado / "proj1").mkdir(parents=True)
    (legado / "proj1" / "a.pdf").write_bytes(b"documento")
    destino = tmp_path / "volume" / "project_documents"

    monkeypatch.setattr(storage, "settings", _settings(monkeypatch, STORAGE_ROOT=str(tmp_path / "volume")))
    monkeypatch.setattr(storage, "LEGACY_DIRS", {"PROJECT_DOCUMENT_DIR": str(legado)})

    assert storage.salvage_legacy_uploads() == {"PROJECT_DOCUMENT_DIR": 1}
    assert (destino / "proj1" / "a.pdf").read_bytes() == b"documento"
    assert (legado / "proj1" / "a.pdf").is_file()  # origem preservada
    assert storage.salvage_legacy_uploads() == {}  # nada a copiar na segunda vez
