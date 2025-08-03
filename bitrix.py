import os
import sys
import requests
import logging
import sqlite3

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
from config import get_param, save_param
import utils

B24_URL = config.B24_URL
LOGGING = config.LOGGING
REDIS_DB = config.REDIS_DB
APP_MODE = config.APP_MODE
APP_DB = config.APP_DB

logging.basicConfig(level=logging.INFO, format='%(message)s', filename='bitrix.log')
logger = logging.getLogger()


def refresh_token():
    member_id = get_param('member_id')
    user_token = get_param('user_token')
    if not member_id or not user_token:
        return False

    payload = {
        'server_id': config.PBX_ID,
        'member_id': member_id,
    }
    server_url = f"{config.CONTROL_SERVER_HTTP}/api/asterx/refresh_token/"

    headers = {
        'Authorization': f'Token {user_token}',
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.post(server_url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error while refreshing token: {e}")
        return False

    try:
        data = resp.json()
        access_token = data.get("access_token")
        if access_token:
            save_param("access_token", access_token)
            return access_token
    except Exception as e:
        print(f"Error parsing response: {e}")
        return False


def call_bitrix(method, payload=None, retried=False):
    if APP_MODE == 'cloud':
        proto = get_param('protocol')
        domain = get_param('domain')
        access_token = get_param('access_token')
        b24_url = f"{proto}://{domain}/rest/{method}?auth={access_token}"
    else:
        b24_url = f'{B24_URL}{method}'
    try:
        resp = requests.post(b24_url, json=payload)
        if resp.status_code == 401 and APP_MODE == 'cloud':
            data = resp.json()
            if data.get('error') == 'expired_token':
                logger.error(data)
                if not retried:  # Защита от вечного цикла
                    new_token = refresh_token()
                    if new_token:
                        return call_bitrix(method, payload=payload, retried=True)
                return None
            else:
                logger.error(f"B24 401 error: {data}")
                return None
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        try:
            logger.error(f'B24 request error: {e}: {resp.json()}')
        except Exception:
            logger.error(f'B24 request error: {e}')
        return None
    if LOGGING in [1,3]:
        logger.info(f"{resp.status_code} {method} {resp.json()}")
    return resp


def get_user_id_remote(user_phone):
    payload = {
        'FILTER': {
            'UF_PHONE_INNER': user_phone
        }
    }
    resp = call_bitrix('user.get', payload)
    resp_data = resp.json()
    resp.raise_for_status()
    result = resp_data.get('result', [])
    if result:
        return result[0].get('ID')
    return get_param('default_user_id', default='1')

def get_user_id(user_phone):
    conn = sqlite3.connect(APP_DB)
    cur = conn.execute("SELECT user_id FROM users WHERE user_phone = ?", (user_phone,))
    row = cur.fetchone()
    if row and row[0]:
        conn.close()
        return row[0]

    # Нет локально, ищем в Bitrix
    remote_id = get_user_id_remote(user_phone)

    # Сохраним в случае успеха (не дефолтного)
    if remote_id and remote_id != get_param('default_user_id', default='1'):
        conn.execute("INSERT OR REPLACE INTO users(user_phone, user_id) VALUES (?, ?)",
                     (user_phone, remote_id))
        conn.commit()
    conn.close()
    return remote_id
    

def register_call(call_data: dict, user_id=None):
    external = call_data.get('external')
    if not external:
        return None
    if not user_id:
        internal = call_data.get('internal')
        if not internal:
            user_id = get_param('default_user_id', default='1')
        else:
            user_id = get_user_id(internal)
    if not user_id:
        return None    

    payload = {
        'USER_ID': user_id,
        'PHONE_NUMBER': external,
        'CRM_CREATE': int(get_param('crm_create', default=0)),
        'SHOW': 1 if int(get_param('show_card', default=0)) == 1 else 0,
        'TYPE': call_data.get('type', 1),
    }
    resp = call_bitrix('telephony.externalcall.register', payload)
    reg_data = resp.json()
    resp.raise_for_status()
    result = reg_data.get('result', {})
    call_id = result.get('CALL_ID')
    return call_id


def upload_file(call_data, file_base64):
    call_id  = call_data.get("call_id")
    if not call_id:
        return None
    payload = {
        'CALL_ID': call_id,
        'FILENAME': os.path.basename(call_data['file_path']),
        'FILE_CONTENT': file_base64
    }
    resp = call_bitrix('telephony.externalCall.attachRecord', payload)


def finish_call(call_data: dict, user_id=None):
    internal = call_data.get('internal')
    if not internal:
        user_id = get_param('default_user_id', default='1')
    else:
        user_id = get_user_id(internal)
    if not user_id:
        return None
    call_id  = call_data.get('call_id')
    if not call_id:
        call_id = register_call(call_data)
        call_data.update({"call_id": call_id})
    if not user_id or not call_id:
        return None
    call_status = call_data.get('status', 403)
    payload = {
        'CALL_ID': call_id,
        'USER_ID': user_id,
        'USER_PHONE_INNER': internal,
        'DURATION': call_data.get('duration', 0),
        'STATUS_CODE': call_status
    }
    resp = call_bitrix('telephony.externalcall.finish', payload)
    resp.raise_for_status()
    if call_status in [200, 'vm']:
        file_base64 = utils.get_file(call_data)
        if file_base64:
            upload_file(call_data, file_base64)
    return resp

def get_user_phone(user_id=None):
    conn = sqlite3.connect(APP_DB)
    if user_id:
        cur = conn.execute("SELECT user_phone, context FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row and row[0] and row[1]:
            conn.close()
            return row[0], row[1]  # (user_phone, context)
        payload = {'ID': user_id}
        resp = call_bitrix('user.get', payload)
        resp.raise_for_status()
        user_data = resp.json().get('result', [])
        user_phone = user_data[0].get('UF_PHONE_INNER')
        if user_data and user_phone:
            # Возможно, контекста нет при первом добавлении
            conn.execute("INSERT OR REPLACE INTO users(user_phone, user_id) VALUES (?, ?)",
                         (user_phone, user_id))
            conn.commit()
            # Попробовать получить контекст только что записанного номера
            cur = conn.execute("SELECT user_phone, context FROM users WHERE user_phone = ?", (user_phone,))
            row = cur.fetchone()
            conn.close()
            if row and row[0] and row[1]:
                return row[0], row[1]
            return None
        conn.close()
        return None

    resp = call_bitrix('user.get')
    resp.raise_for_status()
    users = resp.json().get('result', [])
    for u in users:
        user_id = u.get('ID')
        user_phone = u.get('UF_PHONE_INNER', '')
        if user_id and user_phone:
            cur = conn.execute("UPDATE users SET user_id=? WHERE user_phone=?", (user_id, user_phone))
            if cur.rowcount == 0:
                conn.execute(
                    "INSERT INTO users(user_phone, user_id) VALUES (?, ?)",
                    (user_phone, user_id)
                )
    conn.commit()
    conn.close()

def card_action(call_id, user_phone, action):
    user_id = get_user_id(user_phone)
    if user_id:
        payload = {
            'CALL_ID': call_id,
            'USER_ID': user_id,
        }
        call_bitrix(f"telephony.externalcall.{action}", payload)