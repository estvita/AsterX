# config.py
import sqlite3
import configparser
import threading

config_file = 'config.ini'
config = configparser.ConfigParser()
config.read(config_file)

ENGINE = config.get('app', 'engine', fallback="ami_sql")
APP_DEBUG = config.get('app', 'debug', fallback=0)
APP_MODE = config.get('app', 'mode', fallback="cloud")
APP_PORT = config.get('app', 'port', fallback=8000)
REDIS_DB = config.get('app', 'redis_db', fallback=1)
APP_DB = config.get('app', 'app_db', fallback="app.db")
LOGGING = int(config.get('app', 'logging', fallback=0))
HEARTBEAT_INTERVAL = int(config.get('app', 'heartbeat_interval', fallback=60))
CONTROL_SERVER_WS = config.get('app', 'control_server_ws', fallback="wss://gulin.kz")
CONTROL_SERVER_HTTP = config.get('app', 'control_server_http', fallback="https://gulin.kz")

B24_URL = config.get('bitrix', 'url', fallback=0)
TOKEN = config.get('bitrix', 'token', fallback=0)

PBX_ID = config.get('asterisk', 'pbx_id', fallback=0)
HOSTNAME = config.get('asterisk', 'host', fallback='localhost')
RECORD_PROTOCOL = config.get('asterisk', 'records_protocol', fallback='local')
RECORD_URI = config.get('asterisk', 'records_uri', fallback=0)
RECORD_USER = config.get('asterisk', 'record_user', fallback=0)
RECORD_PASS = config.get('asterisk', 'record_pass', fallback=0)
SSH_KEY = config.get('asterisk', 'key_filepath', fallback=0)
EXTERNAL_CONTEXTS = [s.strip() for s in config.get('asterisk', 'external_contexts', fallback='from-pstn').split(',')]
INTERNAL_CONTEXTS = [s.strip() for s in config.get('asterisk', 'internal_contexts', fallback='from-internal').split(',')]

_DB_READY = False
_APP_CACHE = None
_CONTEXT_CACHE = None
_LOCK = threading.RLock()


def _db_value(value):
    if value is None:
        return None
    return str(value)


def _ensure_db():
    if not _DB_READY:
        prepare_db()


def prepare_db():
    global _DB_READY, _APP_CACHE, _CONTEXT_CACHE

    with _LOCK:
        conn = sqlite3.connect(APP_DB)
        cur = conn.cursor()
        # Таблица context
        cur.execute('''
            CREATE TABLE IF NOT EXISTS context (
                context TEXT PRIMARY KEY,
                type TEXT
            )
        ''')
        # Таблица users
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_phone TEXT PRIMARY KEY,
                user_id TEXT,
                type TEXT,
                context TEXT
            )
        ''')
        # Таблица app
        cur.execute('CREATE TABLE IF NOT EXISTS app (key TEXT PRIMARY KEY, value TEXT)')

        conn.commit()
        conn.close()
        _DB_READY = True
        _APP_CACHE = None
        _CONTEXT_CACHE = None

def clear_table(table):
    global _APP_CACHE, _CONTEXT_CACHE

    if table not in {'app', 'context', 'users'}:
        raise ValueError(f"Unsupported table: {table}")

    _ensure_db()
    conn = sqlite3.connect(APP_DB)
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
    if table == 'app':
        _APP_CACHE = {}
    elif table == 'context':
        _CONTEXT_CACHE = {}
    
def save_param(key, value):
    save_params({key: value})

def save_params(params):
    global _APP_CACHE

    _ensure_db()
    conn = sqlite3.connect(APP_DB)
    cur = conn.cursor()
    for key, value in params.items():
        cur.execute(
            '''
            INSERT INTO app (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            ''',
            (key, _db_value(value))
        )
    conn.commit()
    conn.close()
    if _APP_CACHE is not None:
        _APP_CACHE.update({key: _db_value(value) for key, value in params.items()})

def fetch_from_db(key):
    global _APP_CACHE

    _ensure_db()
    if _APP_CACHE is not None:
        return _APP_CACHE.get(key)

    conn = sqlite3.connect(APP_DB)
    cur = conn.execute("SELECT key, value FROM app")
    _APP_CACHE = dict(cur.fetchall())
    conn.close()
    return _APP_CACHE.get(key)

def update_contexts_table(contexts):
    global _CONTEXT_CACHE

    _ensure_db()
    conn = sqlite3.connect(APP_DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM context")
    context_cache = {}
    for ctx in contexts:
        for context_name, type_value in ctx.items():
            cur.execute("INSERT INTO context (context, type) VALUES (?, ?)", (context_name, type_value))
            context_cache[context_name] = type_value
    conn.commit()
    conn.close()
    _CONTEXT_CACHE = context_cache

def get_param(key, section='app', default=None):
    val = fetch_from_db(key)
    if val is not None:
        return val
    try:
        return config.get(section, key, fallback=default)
    except Exception:
        return default
        
def get_bool_param(key, section='app', default=False):
    value = get_param(key, section=section, default=default)
    if isinstance(value, bool):
        return value
    return str(value).lower() in {'1', 'true', 'yes', 'on'}


def get_context_type(context):
    global _CONTEXT_CACHE

    if APP_MODE == 'local':
        _ensure_db()
        if _CONTEXT_CACHE is None:
            conn = sqlite3.connect(APP_DB)
            cur = conn.execute("SELECT context, type FROM context")
            _CONTEXT_CACHE = dict(cur.fetchall())
            conn.close()
        context_type = _CONTEXT_CACHE.get(context)
        if context_type == 'excluded':
            return None
        if context_type in {'external', 'internal'}:
            return context_type
        if context in EXTERNAL_CONTEXTS:
            return "external"
        elif context in INTERNAL_CONTEXTS:
            return "internal"
        else:
            return None
    elif APP_MODE == 'cloud':
        _ensure_db()
        if _CONTEXT_CACHE is not None:
            return _CONTEXT_CACHE.get(context)

        conn = sqlite3.connect(APP_DB)
        cur = conn.execute("SELECT context, type FROM context")
        _CONTEXT_CACHE = dict(cur.fetchall())
        conn.close()
        return _CONTEXT_CACHE.get(context)
    return None
