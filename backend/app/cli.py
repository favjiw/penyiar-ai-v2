"""Perintah pengelolaan di server (tanpa membuka halaman web).

Contoh, di VPS:
  docker compose exec app python -m app.cli create-user admin --role admin --display-name "Favian"
  docker compose exec -T app python -m app.cli create-user rani --role penyiar --password-stdin <<< "sandi-panjang-ini"
  docker compose exec app python -m app.cli list-users
  docker compose exec app python -m app.cli set-password admin
  docker compose exec app python -m app.cli import-files            # materi lama (file) -> database

Kata sandi tidak pernah diberikan sebagai argumen baris perintah (terbaca di daftar proses dan riwayat shell):
dibaca dari stdin (--password-stdin) atau ditanyakan dua kali.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from sqlalchemy import insert, select

from app.auth import ROLE_RANK, AuthService, UserError
from app.blocker.store import BlockerStore, DbBlockerStore
from app.config import Settings
from app.db import Database, blockers, generation_log, users


def _read_password(args: argparse.Namespace) -> str:
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("Kata sandi: ")
    if first != getpass.getpass("Ulangi kata sandi: "):
        raise SystemExit("Kata sandi tidak sama")
    return first


def _open() -> tuple[Settings, Database, AuthService]:
    settings = Settings()
    url = settings.database_url or "sqlite:///" + (Path(settings.DATA_DIR) / "app.db").as_posix()
    db = Database(url)
    db.create_all()
    return settings, db, AuthService(db, settings)


def cmd_create_user(args: argparse.Namespace) -> None:
    _, _, auth = _open()
    try:
        user = auth.create_user(args.username, _read_password(args), args.role, args.display_name)
    except UserError as e:
        raise SystemExit(f"Gagal: {e}") from e
    print(f"Pengguna dibuat: {user.username} ({user.role})")


def cmd_set_password(args: argparse.Namespace) -> None:
    _, db, auth = _open()
    with db.engine.connect() as conn:
        row = conn.execute(select(users.c.id).where(users.c.username == args.username.strip().lower())).first()
    if row is None:
        raise SystemExit(f"Pengguna '{args.username}' tidak ditemukan")
    try:
        auth.update_user(row.id, password=_read_password(args))
    except UserError as e:
        raise SystemExit(f"Gagal: {e}") from e
    print("Kata sandi diganti; semua sesi login pengguna ini dicabut.")


def cmd_list_users(_: argparse.Namespace) -> None:
    _, _, auth = _open()
    for u in auth.list_users():
        print(f"{u['id']:>3}  {u['username']:<20} {u['role']:<9} {'aktif' if u['active'] else 'NONAKTIF':<9} masuk terakhir: {u['last_login_at'] or '-'}")


def cmd_import_files(args: argparse.Namespace) -> None:
    """Salin materi (DATA_DIR/blockers/*.json) dan catatan pembuatan materi (blocker_generations.jsonl) ke database.
    Aman diulang: yang id-nya sudah ada di database dilewati."""
    settings, db, _ = _open()
    data_dir = Path(args.data_dir or settings.DATA_DIR)
    src = BlockerStore(data_dir)
    dst = DbBlockerStore(db)
    with db.engine.connect() as conn:
        existing = set(conn.execute(select(blockers.c.id)).scalars())
    added = skipped = 0
    for b in src.list():
        if b.id in existing:
            skipped += 1
            continue
        dst.save(b)
        added += 1
    print(f"Materi: {added} disalin, {skipped} sudah ada.")
    log = Path(args.log_dir or settings.LOG_DIR) / "blocker_generations.jsonl"
    if log.is_file():
        with db.engine.connect() as conn:
            have = conn.execute(select(generation_log.c.id)).first() is not None
        if have:
            print("Catatan pembuatan materi: dilewati (tabel sudah berisi).")
        else:
            rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
            with db.engine.begin() as conn:
                for r in rows:
                    conn.execute(insert(generation_log).values(ts=str(r.get("ts", "")), data=r))
            print(f"Catatan pembuatan materi: {len(rows)} baris disalin.")


def cmd_gen_secrets_key(_: argparse.Namespace) -> None:
    from app.secretbox import generate_key

    print(generate_key())


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create-user", help="buat pengguna")
    c.add_argument("username")
    c.add_argument("--role", choices=sorted(ROLE_RANK, key=ROLE_RANK.get), default="penyiar")
    c.add_argument("--display-name", default="")
    c.add_argument("--password-stdin", action="store_true", help="baca kata sandi dari baris pertama stdin")
    c.set_defaults(fn=cmd_create_user)

    s = sub.add_parser("set-password", help="ganti kata sandi pengguna")
    s.add_argument("username")
    s.add_argument("--password-stdin", action="store_true")
    s.set_defaults(fn=cmd_set_password)

    sub.add_parser("list-users", help="daftar pengguna").set_defaults(fn=cmd_list_users)

    sub.add_parser("gen-secrets-key", help="buat SECRETS_KEY (kunci induk enkripsi kunci API) untuk .env server").set_defaults(fn=cmd_gen_secrets_key)

    i = sub.add_parser("import-files", help="salin materi lama (file) ke database")
    i.add_argument("--data-dir", default="")
    i.add_argument("--log-dir", default="")
    i.set_defaults(fn=cmd_import_files)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
