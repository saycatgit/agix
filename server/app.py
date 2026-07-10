"""Agix Auth Server --- RFC 8252 认证服务 (Flask)"""

import os
import re
import sqlite3
import time
import uuid
from pathlib import Path

from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

VALID_CODE = "1234"
TOKEN_EXPIRE_SECONDS = int(os.environ.get("AGIX_TOKEN_EXPIRE_SECONDS", 30 * 24 * 3600))
DB_PATH = os.environ.get("AGIX_DB_PATH", str(Path(__file__).parent / "tokens.db"))


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            token       TEXT PRIMARY KEY,
            phone       TEXT    NOT NULL,
            expires_at  REAL    NOT NULL,
            session_id  TEXT    DEFAULT ''
        )
    """)
    try:
        conn.execute("ALTER TABLE tokens ADD COLUMN session_id TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    conn.execute("DELETE FROM tokens WHERE expires_at <= ?", (time.time(),))
    conn.commit()
    conn.close()


@app.route("/login")
def login_page():
    session_id = request.args.get("session_id", "")
    return render_template("login.html", session_id=session_id)


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    code = (data.get("code") or "").strip()
    session_id = (data.get("session_id") or request.args.get("session_id") or "").strip()

    if not phone:
        return jsonify({"success": False, "error": "请输入手机号"}), 400
    if not code:
        return jsonify({"success": False, "error": "请输入验证码"}), 400
    if not _is_valid_phone(phone):
        return jsonify({"success": False, "error": "手机号格式不正确"}), 400
    if code != VALID_CODE:
        return jsonify({"success": False, "error": "验证码错误"}), 401

    token = uuid.uuid4().hex
    expires_at = time.time() + TOKEN_EXPIRE_SECONDS

    conn = _get_db()
    conn.execute(
        "INSERT INTO tokens (token, phone, expires_at, session_id) VALUES (?, ?, ?, ?)",
        (token, phone, expires_at, session_id),
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True, "token": token, "expires_at": expires_at})


@app.route("/api/poll_login")
def api_poll_login():
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id:
        return jsonify({"token": None})
    conn = _get_db()
    row = conn.execute(
        "SELECT token, expires_at FROM tokens WHERE session_id = ? AND expires_at > ? ORDER BY rowid DESC LIMIT 1",
        (session_id, time.time()),
    ).fetchone()
    conn.close()
    if row:
        return jsonify({"token": row["token"], "expires_at": row["expires_at"]})
    return jsonify({"token": None})


@app.route("/api/verify_token", methods=["POST"])
def api_verify_token():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    if not token:
        return jsonify({"valid": False}), 401
    conn = _get_db()
    row = conn.execute("SELECT phone, expires_at FROM tokens WHERE token = ?", (token,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"valid": False}), 401
    if time.time() > row["expires_at"]:
        conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return jsonify({"valid": False, "error": "token expired"}), 401
    conn.close()
    return jsonify({"valid": True, "phone": row["phone"]})


def _is_valid_phone(phone: str) -> bool:
    return bool(re.match(r"^1[3-9][0-9]{9}$", phone))


_init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
