"""Login por e-mail e senha para o workspace único do TracePilot.

- O primeiro login cria a conta: o e-mail e a senha digitados viram as
  credenciais do workspace (hash PBKDF2 em `workspace/profile.json`).
  Perfis antigos sem senha também caem nesse caso.
- A sessão é um cookie com o e-mail + assinatura HMAC. O segredo vem de
  `TRACEPILOT_SECRET` ou é gerado uma vez em `workspace/secret.key`.

Escopo de hackathon: um workspace só, sem recuperação de senha. Para
recomeçar do zero, apague `workspace/profile.json`.
"""
import hashlib
import hmac
import os
import secrets

from agents import workspace_store
from webapp import presets

ITERATIONS = 200_000
SECRET_FILE = workspace_store.WORKSPACE_FILE.parent / "secret.key"


def _secret() -> bytes:
    env = os.getenv("TRACEPILOT_SECRET")
    if env:
        return env.encode()
    if not SECRET_FILE.exists():
        SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        SECRET_FILE.write_text(secrets.token_hex(32))
        SECRET_FILE.chmod(0o600)
    return SECRET_FILE.read_text().strip().encode()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(candidate, digest)


def _name_from_email(email: str) -> str:
    local = email.split("@")[0].replace(".", " ").replace("_", " ").replace("-", " ")
    return local.strip().title() or email


def authenticate(email: str, password: str) -> dict | None:
    """Devolve o usuário se as credenciais valem (ou se é o primeiro
    acesso, que cria a conta); `None` se não valem."""
    email = email.strip().lower()
    if not email or not password:
        return None
    user = workspace_store.load().get("user") or {}
    stored_hash = user.get("password_hash")
    stored_email = (user.get("email") or "").lower()

    if stored_hash:
        if email != stored_email or not verify_password(password, stored_hash):
            return None
        return user

    preset_user = (presets.active() or {}).get("user") or {}
    if email == stored_email and user.get("name"):
        name = user["name"]
    elif email == (preset_user.get("email") or "").lower() and preset_user.get("name"):
        name = preset_user["name"]
    else:
        name = _name_from_email(email)
    new_user = {"name": name, "email": email, "password_hash": hash_password(password)}
    workspace_store.update(user=new_user)
    return new_user


def has_account() -> bool:
    return bool((workspace_store.load().get("user") or {}).get("password_hash"))


def session_token(email: str) -> str:
    sig = hmac.new(_secret(), email.encode(), hashlib.sha256).hexdigest()
    return f"{email}|{sig}"


def user_from_token(token: str | None) -> dict | None:
    if not token or "|" not in token:
        return None
    email, sig = token.rsplit("|", 1)
    expected = hmac.new(_secret(), email.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    user = workspace_store.load().get("user") or {}
    if (user.get("email") or "").lower() != email:
        return None
    return {"name": user.get("name") or _name_from_email(email), "email": email}
