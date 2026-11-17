"""Perintah pengelolaan di server (tanpa membuka halaman web).

Contoh, di VPS:
  docker compose exec app python -m app.cli create-user admin --role admin --display-name "Favian"
  docker compose exec -T app python -m app.cli create-user rani --role penyiar --password-stdin <<< "sandi-panjang-ini"
  docker compose exec app python -m app.cli list-users
  docker compose exec app python -m app.cli set-password admin
  docker compose exec app python -m app.cli import-files --data-dir /data/data --log-dir /data/logs --sessions-dir /data/sessions
      # data lama (berkas) -> database; aman diulang
  docker compose exec app python -m app.cli prompts list
  docker compose exec app python -m app.cli prompts add persona persona-v5 --file persona-v5.txt   # versi baru, aktif
  docker compose exec app python -m app.cli export-session show_20261117_140000_ab12 --out /data/export
      # log siaran dari database -> berkas JSONL untuk analisis riset

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
from app.blocker.store import BlockerStore
from app.config import Settings
from app.db import Database, blockers, database_for, generation_log, quota_counters, session_blockers, session_events, session_turns, users
from app.schemas import Blocker
from app.session_log import read_events
from app.show.turnlog import read_turns


def _read_password(args: argparse.Namespace) -> str:
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("Kata sandi: ")
    if first != getpass.getpass("Ulangi kata sandi: "):
        raise SystemExit("Kata sandi tidak sama")
    return first


def _open() -> tuple[Settings, Database, AuthService]:
    settings = Settings()
    db = database_for(settings)
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


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def cmd_import_files(args: argparse.Namespace) -> None:
    """Salin data lama berbentuk berkas ke database: materi (blockers/*.json), catatan pembuatan materi, log siaran
    (show_*.jsonl), log giliran (sessions/<id>/turns.jsonl), dan materi per sesi (blocker.json).
    Aman diulang: yang sudah ada di database dilewati."""
    settings, db, _ = _open()
    data_dir = Path(args.data_dir or settings.DATA_DIR)
    log_dir = Path(args.log_dir) if args.log_dir else None
    sessions_dir = Path(args.sessions_dir) if args.sessions_dir else (log_dir.parent / "sessions" if log_dir else None)

    store = BlockerStore(db)
    with db.engine.connect() as conn:
        existing = set(conn.execute(select(blockers.c.id)).scalars())
    added = skipped = 0
    for p in sorted((data_dir / "blockers").glob("blk_*.json")):
        b = Blocker.model_validate_json(p.read_text(encoding="utf-8"))
        if b.id in existing:
            skipped += 1
            continue
        store.save(b)  # apa adanya (termasuk status terkunci)
        added += 1
    print(f"Materi: {added} disalin, {skipped} sudah ada.")
    if log_dir is None:
        return

    gen = log_dir / "blocker_generations.jsonl"
    if gen.is_file():
        with db.engine.connect() as conn:
            have = conn.execute(select(generation_log.c.id)).first() is not None
        if have:
            print("Catatan pembuatan materi: dilewati (tabel sudah berisi).")
        else:
            rows = _jsonl(gen)
            with db.engine.begin() as conn:
                for r in rows:
                    conn.execute(insert(generation_log).values(ts=str(r.get("ts", "")), data=r))
            print(f"Catatan pembuatan materi: {len(rows)} baris disalin.")

    quota = data_dir / "quota.json"
    if quota.is_file():
        q = json.loads(quota.read_text(encoding="utf-8"))
        with db.engine.begin() as conn:
            if conn.execute(select(quota_counters.c.model)).first() is None:
                for model, used in q.get("used", {}).items():
                    conn.execute(insert(quota_counters).values(model=model, day=str(q.get("day", "")), used=int(used), exhausted=model in q.get("exhausted", [])))
                print(f"Kuota: {len(q.get('used', {}))} model disalin.")

    n_sessions = n_skipped = 0
    for f in sorted(log_dir.glob("show_*.jsonl")):
        sid = f.stem
        with db.engine.connect() as conn:
            if conn.execute(select(session_events.c.id).where(session_events.c.session_id == sid)).first():
                n_skipped += 1
                continue
        events = _jsonl(f)
        with db.engine.begin() as conn:
            for ev in events:
                conn.execute(insert(session_events).values(session_id=sid, ts=str(ev.get("ts", "")), type=str(ev.get("type", "")), data=ev))
            turns = sessions_dir / sid / "turns.jsonl" if sessions_dir else None
            if turns and turns.is_file():
                for row in _jsonl(turns):
                    conn.execute(insert(session_turns).values(session_id=sid, turn_idx=int(row.get("turn_idx", 0)), data=row))
            blk = sessions_dir / sid / "blocker.json" if sessions_dir else None
            if blk and blk.is_file():
                conn.execute(insert(session_blockers).values(session_id=sid, data=json.loads(blk.read_text(encoding="utf-8"))))
        n_sessions += 1
    print(f"Log siaran: {n_sessions} sesi disalin, {n_skipped} sudah ada.")


def cmd_export_session(args: argparse.Namespace) -> None:
    """Tulis log sebuah sesi dari database ke berkas: <out>/<id>/{<id>.jsonl, turns.jsonl, blocker.json}
    (bentuk yang dibaca skrip riset: scripts/report.py, scripts/evaluate_pilot.py)."""
    _, db, _ = _open()
    events = read_events(db, args.session_id)
    if not events:
        raise SystemExit(f"Sesi {args.session_id} tidak punya log")
    out = Path(args.out) / args.session_id
    out.mkdir(parents=True, exist_ok=True)

    def dump(path: Path, rows: list[dict]) -> None:
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    dump(out / f"{args.session_id}.jsonl", events)
    dump(out / "turns.jsonl", read_turns(db, args.session_id))
    with db.engine.connect() as conn:
        blk = conn.execute(select(session_blockers.c.data).where(session_blockers.c.session_id == args.session_id)).scalar_one_or_none()
    if blk is not None:
        (out / "blocker.json").write_text(json.dumps(blk, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Diekspor ke {out}")


def cmd_prompts(args: argparse.Namespace) -> None:
    """Prompt berversi di database: lihat, tambah versi baru dari berkas, atau pilih versi yang aktif."""
    from app.content import content

    _, db, _ = _open()
    content.configure(db)
    if args.action == "list":
        for r in content.list_prompts():
            print(f"{r['name']:<12} {r['version']:<16} {'AKTIF' if r['active'] else '':<6} {r['created_at']}  {r['created_by'] or ''}")
    elif args.action == "add":
        body = Path(args.file).read_text(encoding="utf-8")
        content.add_prompt_version(args.name, args.version, body, by="cli", activate=not args.no_activate)
        print(f"Prompt {args.name} versi {args.version} ditambahkan" + ("" if args.no_activate else " dan diaktifkan"))
    else:
        try:
            content.activate_prompt(args.name, args.version)
        except KeyError as e:
            raise SystemExit(str(e)) from e
        print(f"Prompt {args.name} versi {args.version} diaktifkan")


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

    pr = sub.add_parser("prompts", help="kelola prompt berversi di database (list | add | activate)")
    pr.add_argument("action", choices=["list", "add", "activate"])
    pr.add_argument("name", nargs="?", default="")
    pr.add_argument("version", nargs="?", default="")
    pr.add_argument("--file", default="", help="add: berkas isi prompt (tanpa baris versi)")
    pr.add_argument("--no-activate", action="store_true", help="add: simpan tanpa mengaktifkan")
    pr.set_defaults(fn=cmd_prompts)

    sub.add_parser("gen-secrets-key", help="buat SECRETS_KEY (kunci induk enkripsi kunci API) untuk .env server").set_defaults(fn=cmd_gen_secrets_key)

    i = sub.add_parser("import-files", help="salin data lama (berkas) ke database")
    i.add_argument("--data-dir", default="", help="folder berisi blockers/ (bawaan DATA_DIR)")
    i.add_argument("--log-dir", default="", help="folder log lama (show_*.jsonl, blocker_generations.jsonl); kosong = lewati log")
    i.add_argument("--sessions-dir", default="", help="folder sessions/ lama (bawaan: di samping --log-dir)")
    i.set_defaults(fn=cmd_import_files)

    e = sub.add_parser("export-session", help="ekspor log sebuah sesi dari database ke berkas JSONL")
    e.add_argument("session_id")
    e.add_argument("--out", default=".", help="folder tujuan (dibuat subfolder <id>)")
    e.set_defaults(fn=cmd_export_session)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
