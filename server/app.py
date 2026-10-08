"""DeadlineHub mobile sync API. Run behind HTTPS; data is separate from the original website."""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from datetime import date
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
app.config['DATABASE'] = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'deadlinehub-mobile.db'))
CORS(app, resources={r'/api/*': {'origins': os.environ.get('ALLOWED_ORIGINS', 'https://localhost,http://localhost:5173,http://127.0.0.1:5173').split(',')}}, allow_headers=['Authorization', 'Content-Type'])


def db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'], timeout=20)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA journal_mode=WAL')
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db


@app.teardown_appcontext
def close_db(_):
    if 'db' in g:
        g.db.close()


def init_db():
    parent = os.path.dirname(os.path.abspath(app.config['DATABASE']))
    os.makedirs(parent, exist_ok=True)
    with app.app_context():
        db().executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS items(user_id TEXT NOT NULL REFERENCES users(id), id TEXT NOT NULL, rev INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(user_id,id));
        CREATE TABLE IF NOT EXISTS operations(user_id TEXT NOT NULL REFERENCES users(id), op TEXT NOT NULL, conflict INTEGER NOT NULL, PRIMARY KEY(user_id,op));
        CREATE TABLE IF NOT EXISTS limits(key TEXT PRIMARY KEY, count INTEGER NOT NULL, reset REAL NOT NULL);
        ''')
        db().commit()


def fail(message, code=400):
    return jsonify(error=message), code


def payload():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ValueError('A JSON object is required.')
    return value


@app.errorhandler(ValueError)
def invalid(error):
    return fail(str(error))


@app.errorhandler(413)
def too_large(_):
    return fail('Sync payload is too large.', 413)


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def allowed_attempt():
    # Without trusted-proxy configuration, use the socket address, never arbitrary forwarded headers.
    key = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()
    now = time.time()
    conn = db()
    conn.execute('BEGIN IMMEDIATE')
    conn.execute('DELETE FROM limits WHERE reset < ?', (now,))
    conn.execute('INSERT OR IGNORE INTO limits VALUES (?,0,?)', (key, now + 900))
    count = conn.execute('SELECT count FROM limits WHERE key=?', (key,)).fetchone()[0]
    conn.execute('UPDATE limits SET count=count+1 WHERE key=?', (key,))
    conn.commit()
    return count < 30


def credentials():
    data = payload()
    email = data.get('email', '')
    password = data.get('password', '')
    if not isinstance(email, str) or not isinstance(password, str):
        raise ValueError('Invalid email or password.')
    email = email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 254:
        raise ValueError('Enter a valid email.')
    if not 10 <= len(password) <= 256:
        raise ValueError('Use a password between 10 and 256 characters.')
    return email, password


def issue(user):
    token = secrets.token_urlsafe(32)
    db().execute('DELETE FROM tokens WHERE expires < ?', (time.time(),))
    db().execute('INSERT INTO tokens VALUES (?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user['id'], time.time() + 30*86400))
    db().commit()
    return jsonify(token=token, userId=user['id'], email=user['email'])


@app.post('/api/register')
def register():
    if not allowed_attempt():
        return fail('Too many attempts. Try again in 15 minutes.', 429)
    email, password = credentials()
    user_id = str(uuid.uuid4())
    try:
        db().execute('INSERT INTO users VALUES (?,?,?)', (user_id, email, generate_password_hash(password)))
        db().commit()
    except sqlite3.IntegrityError:
        db().rollback()
        return fail('Unable to create this account. Try signing in.', 409)
    return issue({'id': user_id, 'email': email})


@app.post('/api/login')
def login():
    if not allowed_attempt():
        return fail('Too many attempts. Try again in 15 minutes.', 429)
    email, password = credentials()
    user = db().execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    if user is None:
        # Do comparable work for unknown accounts.
        generate_password_hash(password)
        return fail('Incorrect email or password.', 401)
    if not check_password_hash(user['password'], password):
        return fail('Incorrect email or password.', 401)
    return issue(user)


def owner():
    token = request.headers.get('Authorization', '')
    if not token.startswith('Bearer ') or len(token) > 512:
        return None
    found = db().execute('SELECT user_id FROM tokens WHERE hash=? AND expires>?', (hashlib.sha256(token[7:].encode()).hexdigest(), time.time())).fetchone()
    return found['user_id'] if found else None


def clean(raw):
    if not isinstance(raw, dict):
        raise ValueError('Invalid item.')
    for field in ('id', 'op'):
        if not isinstance(raw.get(field), str):
            raise ValueError('Missing item identifier.')
        try:
            uuid.UUID(raw[field])
        except (ValueError, AttributeError):
            raise ValueError('Invalid item identifier.')
    if type(raw.get('rev')) is not int or raw['rev'] < 0:
        raise ValueError('Invalid revision.')
    if raw.get('kind') not in ('note', 'deadline'):
        raise ValueError('Unknown item type.')
    def string(name, limit, default=''):
        value = raw.get(name, default)
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError('Invalid ' + name + '.')
        return value
    title = string('title', 180).strip()
    if not title:
        raise ValueError('Title is required.')
    row = dict(id=raw['id'], kind=raw['kind'], title=title, deleted=raw.get('deleted') is True, updated=string('updated', 60))
    if row['kind'] == 'deadline':
        due = string('due', 10)
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', due):
            raise ValueError('Invalid due date.')
        date.fromisoformat(due)
        if raw.get('priority') not in ('Low', 'Medium', 'High'):
            raise ValueError('Invalid priority.')
        row.update(due=due, category=string('category', 60), priority=raw['priority'], completed=raw.get('completed') is True)
    else:
        row.update(content=string('content', 50000), pinned=raw.get('pinned') is True)
    return row, raw['rev'], raw['op']


@app.post('/api/sync')
def sync():
    user_id = owner()
    if not user_id:
        return fail('Please sign in again. Your offline work is safe.', 401)
    changes = payload().get('changes')
    if not isinstance(changes, list) or len(changes) > 10000:
        return fail('Invalid changes list.')
    changes = [clean(x) for x in changes]  # Validate the complete batch before any writes.
    conn = db()
    conn.execute('BEGIN IMMEDIATE')
    conflicts = 0
    for row, base_rev, op in changes:
        previous = conn.execute('SELECT conflict FROM operations WHERE user_id=? AND op=?', (user_id, op)).fetchone()
        if previous:
            conflicts += previous['conflict']
            continue
        old = conn.execute('SELECT rev,data FROM items WHERE user_id=? AND id=?', (user_id, row['id'])).fetchone()
        rev = old['rev'] if old else 0
        conflict = int(rev != base_rev)
        if conflict:
            conflicts += 1
            if row['deleted']:
                # A stale delete must not remove a newer edit. Keep the server item.
                conn.execute('INSERT INTO operations VALUES (?,?,1)', (user_id, op))
                continue
            row['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, user_id + ':' + op))
            row['title'] = row['title'][:164] + ' (conflict copy)'
            rev = 0
        row['rev'] = rev + 1
        conn.execute('INSERT INTO items VALUES (?,?,?,?) ON CONFLICT(user_id,id) DO UPDATE SET rev=excluded.rev,data=excluded.data', (user_id, row['id'], row['rev'], json.dumps(row)))
        conn.execute('INSERT INTO operations VALUES (?,?,?)', (user_id, op, conflict))
    rows = [json.loads(r['data']) for r in conn.execute('SELECT data FROM items WHERE user_id=?', (user_id,))]
    conn.commit()
    return jsonify(items=rows, conflicts=conflicts)


@app.get('/health')
def health():
    return jsonify(status='ok')


init_db()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8000, debug=False)
