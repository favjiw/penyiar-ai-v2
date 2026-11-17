"""Login aplikasi: pengguna, peran, sesi berbasis cookie, dan pembatas percobaan.

Peran (naik = hak bertambah):
  penyiar  prompter dan pelaporan ucapan; melihat status siaran; memutar audio.
  operator + konsol, materi, mulai/jeda/stop siaran, layar OBS (/stage), suara, cek kesiapan, log.
  admin    + kelola pengguna.

Kata sandi: scrypt (stdlib, tanpa dependensi). Sesi: token acak di cookie HttpOnly; yang disimpan di database
hanya hash-nya. Dengan `AUTH_REQUIRED=false` (pengembangan, tes) semua permintaan dianggap admin lokal.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from starlette.requests import HTTPConnection

from app.blocker.store import now_iso
from app.config import Settings
from app.db import Database, auth_sessions, users

COOKIE = "penyiar_session"
ROLE_RANK = {"penyiar": 1, "operator": 2, "admin": 3}
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
MIN_PASSWORD = 10

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


# ── Kata sandi ───────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, dk = stored.split("$")
        if scheme != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(base64.b64decode(dk)))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password("tidak-dipakai-" + secrets.token_hex(8))  # waktu verifikasi sama untuk pengguna yang tidak ada


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Kata sandi minimal {MIN_PASSWORD} karakter")


# ── Model ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class User:
    id: int
    username: str
    display_name: str
    role: str
    active: bool = True

    def can(self, minimum: str) -> bool:
        return ROLE_RANK.get(self.role, 0) >= ROLE_RANK[minimum]

    def public(self) -> dict:
        d = asdict(self)
        return d


DEV_USER = User(id=0, username="dev", display_name="Pengembangan (tanpa login)", role="admin")


class UserError(ValueError):
    """Kesalahan input pengguna (nama dipakai, peran tidak dikenal, ...) → 422/409 di API."""


def _row_user(r) -> User:
    return User(id=r.id, username=r.username, display_name=r.display_name or r.username, role=r.role, active=bool(r.active))


class LoginThrottle:
    """Blokir sementara setelah gagal login berulang. Dalam memori (satu proses, sesuai arsitektur satu server)."""

    def __init__(self, max_failures: int, window_s: int):
        self.max, self.window = max_failures, window_s
        self._fails: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._fails[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def retry_after(self, key: str) -> int:
        now = time.time()
        q = self._prune(key, now)
        return int(self.window - (now - q[0])) + 1 if len(q) >= self.max else 0

    def fail(self, key: str) -> None:
        self._prune(key, time.time()).append(time.time())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)


class AuthService:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.lifetime_s = settings.AUTH_SESSION_HOURS * 3600
        self.throttle = LoginThrottle(settings.AUTH_MAX_FAILURES, settings.AUTH_LOCKOUT_MIN * 60)

    # pengguna ----------------------------------------------------------------
    def create_user(self, username: str, password: str, role: str, display_name: str = "") -> User:
        username = username.strip().lower()
        if not USERNAME_RE.match(username):
            raise UserError("Nama pengguna 3-32 karakter: huruf kecil, angka, titik, garis bawah, atau strip")
        if role not in ROLE_RANK:
            raise UserError(f"Peran tidak dikenal: {role}")
        try:
            check_password_policy(password)
        except ValueError as e:
            raise UserError(str(e)) from e
        try:
            with self.db.engine.begin() as conn:
                res = conn.execute(
                    insert(users).values(
                        username=username,
                        display_name=display_name.strip()[:100] or username,
                        password_hash=hash_password(password),
                        role=role,
                        active=True,
                        created_at=now_iso(),
                    )
                )
                uid = res.inserted_primary_key[0]
        except IntegrityError as e:
            raise UserError(f"Nama pengguna '{username}' sudah dipakai") from e
        return self.get_user(uid)  # type: ignore[return-value]

    def get_user(self, user_id: int) -> Optional[User]:
        with self.db.engine.connect() as conn:
            r = conn.execute(select(users).where(users.c.id == user_id)).first()
        return _row_user(r) if r else None

    def list_users(self) -> list[dict]:
        with self.db.engine.connect() as conn:
            rows = conn.execute(select(users).order_by(users.c.id)).all()
        return [{**_row_user(r).public(), "created_at": r.created_at, "last_login_at": r.last_login_at} for r in rows]

    def _active_admins(self, conn) -> int:
        return conn.execute(select(func.count()).select_from(users).where(users.c.role == "admin", users.c.active.is_(True))).scalar_one()

    def update_user(self, user_id: int, *, role: str | None = None, active: bool | None = None,
                    display_name: str | None = None, password: str | None = None, acting_id: int | None = None) -> User:
        target = self.get_user(user_id)
        if target is None:
            raise KeyError(user_id)
        values: dict = {}
        if role is not None:
            if role not in ROLE_RANK:
                raise UserError(f"Peran tidak dikenal: {role}")
            values["role"] = role
        if active is not None:
            values["active"] = active
        if display_name is not None:
            values["display_name"] = display_name.strip()[:100] or target.username
        if password is not None:
            try:
                check_password_policy(password)
            except ValueError as e:
                raise UserError(str(e)) from e
            values["password_hash"] = hash_password(password)
        if not values:
            return target
        loses_admin = target.role == "admin" and target.active and (values.get("role", "admin") != "admin" or values.get("active", True) is False)
        with self.db.engine.begin() as conn:
            if loses_admin:
                if user_id == acting_id:
                    raise UserError("Anda tidak bisa menurunkan atau menonaktifkan akun Anda sendiri")
                if self._active_admins(conn) <= 1:
                    raise UserError("Harus tersisa minimal satu admin aktif")
            conn.execute(update(users).where(users.c.id == user_id).values(**values))
            if "password_hash" in values or values.get("active") is False or "role" in values:
                conn.execute(delete(auth_sessions).where(auth_sessions.c.user_id == user_id))  # masuk ulang dengan hak/sandi baru
        return self.get_user(user_id)  # type: ignore[return-value]

    # login -------------------------------------------------------------------
    def authenticate(self, username: str, password: str) -> Optional[User]:
        username = username.strip().lower()
        with self.db.engine.connect() as conn:
            r = conn.execute(select(users).where(users.c.username == username)).first()
        ok = verify_password(password, r.password_hash if r else _DUMMY_HASH)
        if not (r and ok and r.active):
            return None
        with self.db.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == r.id).values(last_login_at=now_iso()))
        return _row_user(r)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create_session(self, user: User, ip: str = "", user_agent: str = "") -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self.db.engine.begin() as conn:
            conn.execute(delete(auth_sessions).where(auth_sessions.c.expires_at < now))  # bersih-bersih sesi kedaluwarsa
            conn.execute(
                insert(auth_sessions).values(
                    token_hash=self._hash_token(token), user_id=user.id, created_at=now,
                    expires_at=now + self.lifetime_s, ip=ip[:64], user_agent=user_agent[:200],
                )
            )
        return token

    def user_for_token(self, token: str) -> Optional[User]:
        """Pengguna pemilik token yang masih berlaku dan aktif; sesi diperpanjang bila sudah lewat separuh umurnya."""
        now = int(time.time())
        h = self._hash_token(token)
        with self.db.engine.connect() as conn:
            r = conn.execute(
                select(users, auth_sessions.c.expires_at)
                .join(auth_sessions, auth_sessions.c.user_id == users.c.id)
                .where(auth_sessions.c.token_hash == h)
            ).first()
        if r is None or r.expires_at < now or not r.active:
            return None
        if r.expires_at - now < self.lifetime_s // 2:
            with self.db.engine.begin() as conn:
                conn.execute(update(auth_sessions).where(auth_sessions.c.token_hash == h).values(expires_at=now + self.lifetime_s))
        return _row_user(r)

    def revoke(self, token: str) -> None:
        with self.db.engine.begin() as conn:
            conn.execute(delete(auth_sessions).where(auth_sessions.c.token_hash == self._hash_token(token)))


# ── Dependensi FastAPI ───────────────────────────────────────────────────────
def user_from_conn(conn: HTTPConnection) -> Optional[User]:
    """Pengguna dari cookie (REST maupun WebSocket). Tanpa AUTH_REQUIRED: admin lokal."""
    settings: Settings = conn.app.state.settings
    if not settings.AUTH_REQUIRED:
        return DEV_USER
    token = conn.cookies.get(COOKIE)
    auth: Optional[AuthService] = getattr(conn.app.state, "auth", None)
    if not token or auth is None:
        return None
    return auth.user_for_token(token)


def require_role(minimum: str):
    """Dependensi: 401 bila belum masuk, 403 bila peran kurang. Sinkron, jadi jalan di threadpool (akses database)."""

    def dep(request: Request) -> User:
        user = user_from_conn(request)
        if user is None:
            raise HTTPException(401, "Belum masuk")
        if not user.can(minimum):
            raise HTTPException(403, "Peran Anda tidak boleh melakukan ini")
        return user

    return dep


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")) or "?"


# ── Rute ─────────────────────────────────────────────────────────────────────
router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=200)


class NewUserRequest(BaseModel):
    username: str
    password: str
    role: str = "penyiar"
    display_name: str = ""


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    active: Optional[bool] = None
    display_name: Optional[str] = None
    password: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current: str
    new: str


def _auth(request: Request) -> AuthService:
    auth = getattr(request.app.state, "auth", None)
    if auth is None:
        raise HTTPException(404, "Login tidak diaktifkan")
    return auth


@router.post("/api/auth/login")
def login(req: LoginRequest, request: Request, response: Response):
    auth = _auth(request)
    settings: Settings = request.app.state.settings
    uname = req.username.strip().lower()
    keys = (f"u:{uname}", f"ip:{client_ip(request)}")
    wait = max(auth.throttle.retry_after(keys[0]), auth.throttle.retry_after(keys[1]))
    if wait:
        raise HTTPException(429, f"Terlalu banyak percobaan gagal. Coba lagi dalam {max(1, wait // 60)} menit.", headers={"Retry-After": str(wait)})
    user = auth.authenticate(req.username, req.password)
    if user is None:
        for k in keys:
            auth.throttle.fail(k)
        raise HTTPException(401, "Nama pengguna atau kata sandi salah")
    auth.throttle.reset(keys[0])
    token = auth.create_session(user, client_ip(request), request.headers.get("user-agent", ""))
    response.set_cookie(
        COOKIE, token, max_age=auth.lifetime_s, httponly=True, samesite="lax", secure=settings.AUTH_COOKIE_SECURE, path="/",
    )
    return {"user": user.public()}


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    auth = getattr(request.app.state, "auth", None)
    if token and auth:
        auth.revoke(token)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/api/auth/me")
def me(request: Request):
    settings: Settings = request.app.state.settings
    user = user_from_conn(request)
    if user is None:
        raise HTTPException(401, "Belum masuk")
    return {"user": user.public(), "auth_required": settings.AUTH_REQUIRED}


@router.post("/api/auth/password")
def change_password(req: ChangePasswordRequest, request: Request, user: User = Depends(require_role("penyiar"))):
    auth = _auth(request)
    if auth.authenticate(user.username, req.current) is None:
        raise HTTPException(403, "Kata sandi saat ini salah")
    try:
        auth.update_user(user.id, password=req.new)
    except UserError as e:
        raise HTTPException(422, str(e)) from e
    return {"ok": True}  # semua sesi pengguna ini dicabut (termasuk yang sekarang): masuk ulang


@router.get("/api/users")
def list_users(request: Request, _: User = Depends(require_role("admin"))):
    return _auth(request).list_users()


@router.post("/api/users", status_code=201)
def create_user(req: NewUserRequest, request: Request, _: User = Depends(require_role("admin"))):
    try:
        return _auth(request).create_user(req.username, req.password, req.role, req.display_name).public()
    except UserError as e:
        raise HTTPException(409 if "sudah dipakai" in str(e) else 422, str(e)) from e


@router.patch("/api/users/{user_id}")
def patch_user(user_id: int, req: UpdateUserRequest, request: Request, admin: User = Depends(require_role("admin"))):
    try:
        return _auth(request).update_user(
            user_id, role=req.role, active=req.active, display_name=req.display_name, password=req.password, acting_id=admin.id
        ).public()
    except KeyError:
        raise HTTPException(404, "Pengguna tidak ditemukan") from None
    except UserError as e:
        raise HTTPException(422, str(e)) from e
