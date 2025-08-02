# config.py
import sqlite3
import configparser

config_file = 'config.ini'
config = configparser.ConfigParser()
config.read(config_file)

ENGINE = config.get('app', 'engine', fallback="ami_sql")
APP_MODE = config.get('app', 'mode', fallback="cloud")
REDIS_DB = config.get('app', 'redis_db', fallback=1)
APP_DB = config.get('app', 'app_db', fallback="app.db")
LOGGING = int(config.get('app', 'logging', fallback=0))
VM_SEND = config.get('app', 'vm_send', fallback="1")
CONTROL_SERVER_WS = config.get('app', 'control_server_ws', fallback="wss://gulin.kz")
CONTROL_SERVER_HTTP = config.get('app', 'control_server_http', fallback="https://gulin.kz")

B24_URL = config.get('bitrix', 'url', fallback=0)

PBX_ID = config.get('asterisk', 'pbx_id', fallback=0)
HOSTNAME = config.get('asterisk', 'host', fallback='localhost')
RECORD_PROTOCOL = config.get('asterisk', 'records_protocol', fallback='local')
RECORD_URI = config.get('asterisk', 'records_uri', fallback=0)
RECORD_USER = config.get('asterisk', 'record_user', fallback=0)
RECORD_PASS = config.get('asterisk', 'record_pass', fallback=0)
SSH_KEY = config.get('asterisk', 'key_filepath', fallback=0)
EXTERNAL_CONTEXTS = [s.strip() for s in config.get('asterisk', 'external_contexts', fallback='from-pstn').split(',')]
INTERNAL_CONTEXTS = [s.strip() for s in config.get('asterisk', 'internal_contexts', fallback='from-internal').split(',')]

def prepare_db():
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
    # Calls
    conn.execute('''
    CREATE TABLE IF NOT EXISTS calls (
        linked_id TEXT PRIMARY KEY,
        start_time REAL,
        context TEXT,
        uniqueid TEXT,
        type INTEGER,
        external TEXT,
        internal TEXT,
        call_id TEXT,
        file_path TEXT,
        status INTEGER
    )
    ''')
    # Таблица app
    cur.execute('CREATE TABLE IF NOT EXISTS app (key TEXT PRIMARY KEY, value TEXT)')
    conn.commit()
    conn.close()

def clear_table(table):
    conn = sqlite3.connect(APP_DB)
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
    
def save_param(key, value):
    conn = sqlite3.connect(APP_DB)
    cur = conn.cursor()
    cur.execute(
        '''
        INSERT INTO app (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        ''',
        (key, value)
    )
    conn.commit()
    conn.close()

def fetch_from_db(key):
    prepare_db()
    conn = sqlite3.connect(APP_DB)
    cur = conn.execute(f"SELECT value FROM app WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    if row:
        return row[0]
    return None

def update_contexts_table(contexts):
    conn = sqlite3.connect(APP_DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM context")
    for ctx in contexts:
        for context_name, type_value in ctx.items():
            cur.execute("INSERT INTO context (context, type) VALUES (?, ?)", (context_name, type_value))
    conn.commit()
    conn.close()

def get_param(key, section='app', default=None):
    # Если локальный режим — только config
    if APP_MODE == 'local':
        try:
            return config.get(section, key, fallback=default)
        except Exception:
            return default
    elif APP_MODE == 'cloud':
        val = fetch_from_db(key)
        if val is not None:
            return val
        try:
            return config.get(section, key, fallback=default)
        except Exception:
            return default
        

def get_context_type(context):
    conn = sqlite3.connect(APP_DB)
    cur = conn.execute("SELECT type FROM context WHERE context=?", (context,))
    row = cur.fetchone()
    conn.close()
    if row:
        return row[0]
    return None
        

CRM_CREATE = int(get_param('crm_create', default=0))
SHOW_CARD = int(get_param('show_card', default=1))
DEFAULT_USER_ID = get_param('default_user_id', default='1')
