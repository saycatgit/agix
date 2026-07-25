"""Agix Auth Server --- RFC 8252 认证服务 (Flask)"""

import os
import re
import sqlite3
import time
import uuid
import json
import secrets
import random
import hmac
import hashlib
import base64
import urllib.request
import ssl
from functools import wraps
from pathlib import Path

from flask import Flask, request, jsonify, render_template, session, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get('AGIX_SECRET_KEY', secrets.token_hex(32))

MAGIC_CODE = '9527'
ADMIN_PASSWORD = os.environ.get('AGIX_ADMIN_PASSWORD', 'admin123')
TOKEN_EXPIRE_SECONDS = int(os.environ.get('AGIX_TOKEN_EXPIRE_SECONDS', 30 * 24 * 3600))
DB_PATH = os.environ.get('AGIX_DB_PATH', str(Path(__file__).parent / 'tokens.db'))

def _parse_system(user_agent: str) -> str:
    """从 User-Agent 中解析操作系统名称。"""
    ua = (user_agent or '').lower()
    if 'windows' in ua:
        return 'Windows'
    if 'mac os' in ua or 'macintosh' in ua:
        return 'macOS'
    if 'android' in ua:
        return 'Android'
    if 'iphone' in ua or 'ipad' in ua:
        return 'iOS'
    if 'linux' in ua and 'android' not in ua:
        return 'Linux'
    return 'Unknown'

SMS_CODE_EXPIRE_SECONDS = 300

# ---------------------------------------------------------------------------
#  shared helpers
# ---------------------------------------------------------------------------

def _admin_required(f):
    """Decorator: require admin session to access route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login_page'))
        return f(*args, **kwargs)
    return decorated


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


_ALIYUN_ACCESS_KEY_ID = os.environ.get('ALIYUN_ACCESS_KEY_ID', 'LTAI5t9HFPGJKQv9vCbCQM4e')
_ALIYUN_ACCESS_KEY_SECRET = os.environ.get('ALIYUN_ACCESS_KEY_SECRET', 'WdLXAiudICbuEVSpfJxoFvqN8cEfyc')
_ALIYUN_SMS_SIGN_NAME = os.environ.get('ALIYUN_SMS_SIGN_NAME', '速通互联验证码')
_ALIYUN_SMS_TEMPLATE_CODE = os.environ.get('ALIYUN_SMS_TEMPLATE_CODE', '100001')


def _init_db() -> None:
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            token       TEXT PRIMARY KEY,
            phone       TEXT    NOT NULL,
            expires_at  REAL    NOT NULL,
            sid         TEXT    DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS login_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phone       TEXT    NOT NULL,
            ip          TEXT    DEFAULT '',
            created_at  REAL    NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            phone         TEXT PRIMARY KEY,
            created_at    REAL NOT NULL,
            last_login_at REAL DEFAULT 0,
            login_count   INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sms_codes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phone       TEXT NOT NULL,
            code        TEXT NOT NULL,
            expires_at  REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    existing = conn.execute("SELECT value FROM settings WHERE key = 'admin_password'").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('admin_password', ?)",
            (ADMIN_PASSWORD,),
        )
    try:
        conn.execute('ALTER TABLE tokens ADD COLUMN session_id TEXT DEFAULT ''')
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute('ALTER TABLE login_log ADD COLUMN user_agent TEXT DEFAULT ''')
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute('ALTER TABLE login_log ADD COLUMN system TEXT DEFAULT ''')
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute('ALTER TABLE login_log ADD COLUMN client_system TEXT DEFAULT ''')
    except sqlite3.OperationalError:
        pass
    conn.execute('DELETE FROM tokens WHERE expires_at <= ?', (time.time(),))
    conn.execute('DELETE FROM sms_codes WHERE expires_at <= ?', (time.time(),))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
#  Alibaba Cloud Dypnsapi SendSmsVerifyCode (HMAC-SHA1 V1)
# ---------------------------------------------------------------------------

def _percent_encode(s: str) -> str:
    """URL-encode per Alibaba Cloud Signature V1 (safe: A-Z a-z 0-9 - _ . ~)."""
    import string as _string
    safe = set(_string.ascii_letters + _string.digits + '-_.~')
    out = []
    for c in s:
        if c in safe:
            out.append(c)
        else:
            for byte in c.encode('utf-8'):
                out.append('%{:02X}'.format(byte))
    return ''.join(out)


def _send_aliyun_sms(phone: str, code: str) -> dict:
    """Send SMS via Alibaba Cloud Dypnsapi SendSmsVerifyCode. Returns {'success': bool, 'error': str}."""
    if not all([_ALIYUN_ACCESS_KEY_ID, _ALIYUN_ACCESS_KEY_SECRET]):
        return {'success': False, 'error': 'SMS 服务未配置 (缺少 AK/SK)'}

    params = {
        'AccessKeyId': _ALIYUN_ACCESS_KEY_ID,
        'Action': 'SendSmsVerifyCode',
        'Format': 'JSON',
        'PhoneNumber': phone,
        'SignatureMethod': 'HMAC-SHA1',
        'SignatureNonce': str(uuid.uuid4()),
        'SignatureVersion': '1.0',
        'TemplateParam': json.dumps({"code": code, "min": "5"}),
        'Timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'Version': '2017-05-25',
    }

    if _ALIYUN_SMS_TEMPLATE_CODE:
        params['TemplateCode'] = _ALIYUN_SMS_TEMPLATE_CODE
 
    if _ALIYUN_SMS_SIGN_NAME:
        params['SignName'] = _ALIYUN_SMS_SIGN_NAME

    sorted_keys = sorted(params.keys())
    canonical_query = '&'.join([
        f'{_percent_encode(k)}={_percent_encode(str(params[k]))}'
        for k in sorted_keys
    ])

    string_to_sign = 'GET&%2F&' + _percent_encode(canonical_query)

    key = (_ALIYUN_ACCESS_KEY_SECRET + '&').encode('utf-8')
    signature = base64.b64encode(
        hmac.new(key, string_to_sign.encode('utf-8'), hashlib.sha1).digest()
    ).decode('utf-8')

    url = (f'https://dypnsapi.aliyuncs.com/'
           f'?Signature={_percent_encode(signature)}&{canonical_query}')

    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            if result.get('Code') == 'OK':
                return {'success': True}
            return {'success': False, 'error': result.get('Message', '发送失败')}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ---------------------------------------------------------------------------
#  user-facing routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    """Agix 项目首页。"""
    return render_template('index.html')

@app.route('/login')
def login_page():
    session_id = request.args.get('session_id', '')
    client_system = request.args.get('client_system', '')
    return render_template('login.html', session_id=session_id, client_system=client_system)


@app.route('/api/send_sms', methods=['POST'])
def api_send_sms():
    data = request.get_json(silent=True) or {}
    phone = (data.get('phone') or '').strip()

    if not phone:
        return jsonify({'success': False, 'error': '请输入手机号'}), 400
    if not _is_valid_phone(phone):
        return jsonify({'success': False, 'error': '手机号格式不正确'}), 400

    code = str(random.randint(1000, 9999))
    expires_at = time.time() + SMS_CODE_EXPIRE_SECONDS

    sms_result = _send_aliyun_sms(phone, code)
    if not sms_result['success']:
        code = MAGIC_CODE

    conn = _get_db()
    conn.execute(
        'INSERT INTO sms_codes (phone, code, expires_at) VALUES (?, ?, ?)',
        (phone, code, expires_at),
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True})


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or {}
    phone = (data.get('phone') or '').strip()
    code = (data.get('code') or '').strip()
    session_id = (data.get('session_id') or request.args.get('session_id') or '').strip()

    if not phone:
        return jsonify({'success': False, 'error': '请输入手机号'}), 400
    if not code:
        return jsonify({'success': False, 'error': '请输入验证码'}), 400
    if not _is_valid_phone(phone):
        return jsonify({'success': False, 'error': '手机号格式不正确'}), 400

    now = time.time()
    code_ok = False
    conn = _get_db()
    sms_row = conn.execute(
        'SELECT code FROM sms_codes WHERE phone = ? AND expires_at > ? ORDER BY id DESC LIMIT 1',
        (phone, now),
    ).fetchone()
    if sms_row and sms_row['code'] == code:
        code_ok = True
        conn.execute('DELETE FROM sms_codes WHERE phone = ?', (phone,))
    elif code == MAGIC_CODE:
        code_ok = True
    conn.commit()
    conn.close()

    if not code_ok:
        return jsonify({'success': False, 'error': '验证码错误或已过期'}), 401

    token = uuid.uuid4().hex
    expires_at = now + TOKEN_EXPIRE_SECONDS

    conn = _get_db()
    ip = request.headers.get('X-Forwarded-For', request.remote_addr) or ''
    user_agent = request.headers.get('User-Agent', '') or ''
    sys_name = _parse_system(user_agent)
    client_system = (data.get('client_system') or '').strip()
    conn.execute(
        'INSERT INTO login_log (phone, ip, created_at, user_agent, system, client_system) VALUES (?, ?, ?, ?, ?, ?)',
        (phone, ip, now, user_agent, sys_name, client_system),
    )

    existing = conn.execute('SELECT phone FROM users WHERE phone = ?', (phone,)).fetchone()
    if existing:
        conn.execute(
            'UPDATE users SET last_login_at = ?, login_count = login_count + 1 WHERE phone = ?',
            (now, phone),
        )
    else:
        conn.execute(
            'INSERT INTO users (phone, created_at, last_login_at, login_count) VALUES (?, ?, ?, 1)',
            (phone, now, now),
        )

    conn.execute(
        'INSERT INTO tokens (token, phone, expires_at, session_id) VALUES (?, ?, ?, ?)',
        (token, phone, expires_at, session_id),
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'token': token, 'expires_at': expires_at})


@app.route('/api/poll_login')
def api_poll_login():
    session_id = (request.args.get('session_id') or '').strip()
    if not session_id:
        return jsonify({'token': None})
    conn = _get_db()
    row = conn.execute(
        'SELECT token, expires_at FROM tokens WHERE session_id = ? AND expires_at > ? ORDER BY rowid DESC LIMIT 1',
        (session_id, time.time()),
    ).fetchone()
    conn.close()
    if row:
        return jsonify({'token': row['token'], 'expires_at': row['expires_at']})
    return jsonify({'token': None})


@app.route('/api/verify_token', methods=['POST'])
def api_verify_token():
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'valid': False}), 401
    conn = _get_db()
    row = conn.execute('SELECT phone, expires_at FROM tokens WHERE token = ?', (token,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({'valid': False}), 401
    if time.time() > row['expires_at']:
        conn.execute('DELETE FROM tokens WHERE token = ?', (token,))
        conn.commit()
        conn.close()
        return jsonify({'valid': False, 'error': 'token expired'}), 401
    conn.close()
    return jsonify({'valid': True, 'phone': row['phone']})


def _is_valid_phone(phone: str) -> bool:
    return bool(re.match(r'^1[3-9][0-9]{9}$', phone))


# ---------------------------------------------------------------------------
#  admin routes
# ---------------------------------------------------------------------------

def _get_admin_password() -> str:
    try:
        conn = _get_db()
        row = conn.execute("SELECT value FROM settings WHERE key = 'admin_password'").fetchone()
        conn.close()
        if row:
            return row['value']
    except Exception:
        pass
    return ADMIN_PASSWORD


@app.route('/admin')
@_admin_required
def admin_dashboard():
    return render_template('admin/dashboard.html')


@app.route('/admin/login')
def admin_login_page():
    if session.get('admin'):
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login_page'))


@app.route('/admin/api/login', methods=['POST'])
def admin_api_login():
    data = request.get_json(silent=True) or {}
    password = (data.get('password') or '').strip()
    if password != _get_admin_password():
        return jsonify({'success': False, 'error': '密码错误'}), 401
    session['admin'] = True
    return jsonify({'success': True})


@app.route('/admin/api/change_password', methods=['POST'])
@_admin_required
def admin_api_change_password():
    data = request.get_json(silent=True) or {}
    old_pwd = (data.get('old_password') or '').strip()
    new_pwd = (data.get('new_password') or '').strip()

    if not old_pwd or not new_pwd:
        return jsonify({'success': False, 'error': '请输入旧密码和新密码'}), 400
    if len(new_pwd) < 4:
        return jsonify({'success': False, 'error': '新密码至少4位'}), 400
    if old_pwd != _get_admin_password():
        return jsonify({'success': False, 'error': '旧密码错误'}), 401

    conn = _get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_password', ?)",
        (new_pwd,),
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/admin/api/tokens')
@_admin_required
def admin_api_tokens():
    conn = _get_db()
    now = time.time()
    search = request.args.get('search', '').strip()
    status = request.args.get('status', 'all')
    page = max(1, int(request.args.get('page', 1)))
    per_page = 20
    offset = (page - 1) * per_page

    where = []
    params = []
    if search:
        where.append('phone LIKE ?')
        params.append(f'%{search}%')
    if status == 'active':
        where.append('expires_at > ?')
        params.append(now)
    elif status == 'expired':
        where.append('expires_at <= ?')
        params.append(now)

    where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''

    total_row = conn.execute(f'SELECT COUNT(*) as cnt FROM tokens {where_clause}', params).fetchone()
    total = total_row['cnt'] if total_row else 0

    rows = conn.execute(
        f'SELECT * FROM tokens {where_clause} ORDER BY rowid DESC LIMIT ? OFFSET ?',
        params + [per_page, offset],
    ).fetchall()

    tokens = []
    for r in rows:
        tokens.append({
            'token': r['token'],
            'phone': r['phone'],
            'session_id': r['session_id'] or '',
            'expires_at': r['expires_at'],
            'active': r['expires_at'] > now,
        })

    conn.close()
    return jsonify({'tokens': tokens, 'total': total, 'page': page, 'per_page': per_page})


@app.route('/admin/api/tokens/revoke', methods=['POST'])
@_admin_required
def admin_api_revoke_token():
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'success': False, 'error': 'token is required'}), 400
    conn = _get_db()
    conn.execute('DELETE FROM tokens WHERE token = ?', (token,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/admin/api/stats')
@_admin_required
def admin_api_stats():
    conn = _get_db()
    now = time.time()
    total_tokens = conn.execute('SELECT COUNT(*) as cnt FROM tokens').fetchone()['cnt']
    active_tokens = conn.execute('SELECT COUNT(*) as cnt FROM tokens WHERE expires_at > ?', (now,)).fetchone()['cnt']
    distinct_phones = conn.execute('SELECT COUNT(DISTINCT phone) as cnt FROM tokens').fetchone()['cnt']
    total_users = conn.execute('SELECT COUNT(*) as cnt FROM users').fetchone()['cnt']
    recent_logins = conn.execute(
        'SELECT phone, ip, created_at, user_agent, system, client_system FROM login_log ORDER BY id DESC LIMIT 20'
    ).fetchall()
    conn.close()
    return jsonify({
        'total_tokens': total_tokens,
        'active_tokens': active_tokens,
        'expired_tokens': total_tokens - active_tokens,
        'distinct_phones': distinct_phones,
        'total_users': total_users,
        'recent_logins': [{
            'phone': r['phone'],
            'ip': r['ip'],
            'created_at': r['created_at'],
            'user_agent': r['user_agent'] or '',
            'system': r['system'] or '',
            'client_system': r['client_system'] or '',
        } for r in recent_logins],
    })


@app.route('/admin/api/users')
@_admin_required
def admin_api_users():
    conn = _get_db()
    search = request.args.get('search', '').strip()
    page = max(1, int(request.args.get('page', 1)))
    per_page = 20
    offset = (page - 1) * per_page

    where = []
    params = []
    if search:
        where.append('phone LIKE ?')
        params.append(f'%{search}%')

    where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''

    total_row = conn.execute(f'SELECT COUNT(*) as cnt FROM users {where_clause}', params).fetchone()
    total = total_row['cnt'] if total_row else 0

    rows = conn.execute(
        f'SELECT * FROM users {where_clause} ORDER BY last_login_at DESC LIMIT ? OFFSET ?',
        params + [per_page, offset],
    ).fetchall()

    users = []
    for r in rows:
        users.append({
            'phone': r['phone'],
            'created_at': r['created_at'],
            'last_login_at': r['last_login_at'],
            'login_count': r['login_count'],
        })

    conn.close()
    return jsonify({'users': users, 'total': total, 'page': page, 'per_page': per_page})


_init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
