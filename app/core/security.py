import logging
from datetime import datetime, timedelta

from jose import jwt, JWTError
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Ordem: bcrypt primeiro = novos hashes; demais = compatibilidade com registros antigos.
pwd_context = CryptContext(
    schemes=["bcrypt", "argon2", "pbkdf2_sha256"],
    deprecated="auto",
)


class PasswordHashingError(Exception):
    """Falha ao gerar hash de senha (passlib/bcrypt)."""


def normalize_password_for_bcrypt(password: str | object) -> str:
    """
    bcrypt aceita no máximo 72 bytes; trunca UTF-8 sem cortar no meio de um caractere.
    """
    if not isinstance(password, str):
        password = str(password)
    data = password.encode("utf-8")
    if len(data) <= 72:
        return password
    truncated = data[:72]
    while truncated:
        try:
            return truncated.decode("utf-8")
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return ""


def hash_password(password: str) -> str:
    """Novos hashes: primeiro esquema do contexto (bcrypt)."""
    pwd = normalize_password_for_bcrypt(password)
    try:
        return pwd_context.hash(pwd)
    except Exception:
        logger.exception("Falha ao gerar hash de senha (passlib/bcrypt)")
        raise PasswordHashingError("Não foi possível processar a senha.") from None


def verify_password(password: str, hashed: str) -> bool:
    """Verifica senha sem alterar o hash (ex.: testes ou fluxos que não persistem)."""
    if not hashed:
        return False
    pwd = normalize_password_for_bcrypt(password)
    try:
        return pwd_context.verify(pwd, hashed)
    except UnknownHashError:
        logger.warning(
            "Hash de senha não reconhecido pelo passlib (algoritmo desconhecido ou hash corrompido)."
        )
        return False
    except ValueError as e:
        logger.warning("Erro ao verificar senha: %s", e)
        return False
    except Exception:
        logger.exception("Falha inesperada em verify_password (passlib/bcrypt)")
        return False


def verify_password_and_maybe_rehash(password: str, hashed: str) -> tuple[bool, str | None]:
    """
    Verifica a senha e, se estiver correta e o hash for legado, devolve novo hash em bcrypt.
    Retorna (ok, novo_hash_ou_none). Se novo_hash for str, persistir em user.password_hash.
    """
    if not hashed:
        return False, None
    pwd = normalize_password_for_bcrypt(password)
    try:
        valid, new_hash = pwd_context.verify_and_update(pwd, hashed)
        if not valid:
            return False, None
        return True, new_hash
    except UnknownHashError:
        logger.warning(
            "Hash de senha não reconhecido pelo passlib (algoritmo desconhecido ou hash corrompido)."
        )
        return False, None
    except ValueError as e:
        logger.warning("Erro ao verificar senha: %s", e)
        return False, None
    except Exception:
        logger.exception("Falha inesperada em verify_password_and_maybe_rehash (passlib/bcrypt)")
        return False, None


def create_access_token(data: dict, expires_delta: int = 60 * 24) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_delta)
    to_encode.update({"exp": int(expire.timestamp())})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return {}


def normalize_token(token: str) -> str:
    if not token:
        return ""
    t = token.strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return t
