import os
import sys
import requests
import logging
import sqlite3
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
from config import get_param, save_params
import utils
import ami_tools

LOGGING = config.LOGGING
REDIS_DB = config.REDIS_DB
APP_MODE = config.APP_MODE
APP_DB = config.APP_DB

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', filename='bitrix.log')
logger = logging.getLogger()


def save_install_auth(form):
    current_member_id = config.fetch_from_db('member_id')
    incoming_member_id = form.get('auth[member_id]')
    if current_member_id and incoming_member_id and current_member_id != incoming_member_id:
        logger.error(
            f"B24 install rejected: current member_id={current_member_id}, incoming member_id={incoming_member_id}"
        )
        return None

    field_map = {
        'access_token': 'auth[access_token]',
        'refresh_token': 'auth[refresh_token]',
        'expires': 'auth[expires]',
        'expires_in': 'auth[expires_in]',
        'scope': 'auth[scope]',
        'domain': 'auth[domain]',
        'server_endpoint': 'auth[server_endpoint]',
        'client_endpoint': 'auth[client_endpoint]',
        'member_id': 'auth[member_id]',
        'user_id': 'auth[user_id]',
        'application_token': 'auth[application_token]',
    }
    params = {
        key: form.get(form_key)
        for key, form_key in field_map.items()
        if form.get(form_key)
    }
    for key in ('client_id', 'client_secret'):
        value = form.get(key) or form.get(f'auth[{key}]')
        if value:
            params[key] = value
    if params:
        save_params(params)
    return params


def save_oauth_response(data):
    keys = (
        'access_token',
        'refresh_token',
        'expires',
        'expires_in',
        'scope',
        'member_id',
        'user_id',
        'status',
    )
    params = {key: data.get(key) for key in keys if data.get(key) is not None}
    if params:
        save_params(params)
    return params


def bind_events(handler_url):
    for event in ('ONEXTERNALCALLSTART', 'ONEXTERNALCALLBACKSTART'):
        call_bitrix('event.bind', {
            'event': event,
            'handler': handler_url,
        })


def refresh_token():
    if APP_MODE == 'cloud':
        member_id = get_param('member_id')
        if not member_id:
            return False

        payload = {
            'server_id': config.PBX_ID,
            'member_id': member_id,
        }
        server_url = f"{config.CONTROL_SERVER_HTTP}/api/asterx/refresh_token/"

        headers = {
            'Content-Type': 'application/json'
        }

        try:
            resp = requests.post(server_url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error while refreshing token: {e}")
            return False

        try:
            data = resp.json()
            access_token = data.get("access_token")
            if access_token:
                save_params({"access_token": access_token})
                return access_token
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return False

    refresh_token_value = config.fetch_from_db('refresh_token')
    client_id = config.fetch_from_db('client_id')
    client_secret = config.fetch_from_db('client_secret')
    if not refresh_token_value or not client_id or not client_secret:
        logger.error("B24 OAuth credentials are not configured")
        return False

    payload = {
        'grant_type': 'refresh_token',
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token_value,
    }

    try:
        resp = requests.get('https://oauth.bitrix24.tech/oauth/token/', params=payload, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error while refreshing token: {e}")
        return False

    try:
        data = resp.json()
        access_token = data.get("access_token")
        if access_token:
            save_oauth_response(data)
            return access_token
    except Exception as e:
        logger.error(f"Error parsing response: {e}")
        return False


def call_bitrix(method, payload=None, retried=False):
    if APP_MODE == 'cloud':
        proto = get_param('protocol')
        domain = get_param('domain')
        access_token = get_param('access_token')
        if not proto or not domain or not access_token:
            logger.error(f"B24 cloud credentials are not configured for method {method}")
            return None
        b24_url = f"{proto}://{domain}/rest/{method}?auth={access_token}"
    else:
        client_endpoint = config.fetch_from_db('client_endpoint')
        access_token = config.fetch_from_db('access_token')
        if client_endpoint and access_token:
            b24_url = f"{client_endpoint.rstrip('/')}/{method}?auth={access_token}"
        elif config.B24_URL:
            b24_url = f"{config.B24_URL.rstrip('/')}/{method}"
        else:
            logger.error(f"B24 local credentials are not configured for method {method}")
            return None
    try:
        resp = requests.post(b24_url, json=payload)
        if resp.status_code == 401:
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
    if not resp:
        return get_param('default_user_id', section='bitrix', default='1')
    resp_data = resp.json()
    resp.raise_for_status()
    result = resp_data.get('result', [])
    if result:
        return result[0].get('ID')
    return get_param('default_user_id', section='bitrix', default='1')

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
    if remote_id and remote_id != get_param('default_user_id', section='bitrix', default='1'):
        conn.execute(
            '''
            INSERT INTO users(user_phone, user_id)
            VALUES (?, ?)
            ON CONFLICT(user_phone) DO UPDATE SET user_id=excluded.user_id
            ''',
            (user_phone, remote_id)
        )
        conn.commit()
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(ami_tools.update_peer_context(user_phone))
        except RuntimeError:
            asyncio.run(ami_tools.update_peer_context(user_phone))
    conn.close()
    return remote_id
    

def register_call(call_data: dict, user_id=None):
    external = call_data.get('external')
    if not external:
        return None
    if not user_id:
        internal = call_data.get('internal')
        if not internal:
            user_id = get_param('default_user_id', section='bitrix', default='1')
        else:
            user_id = get_user_id(internal)
    if not user_id:
        return None
    
    crm_create_setting = int(get_param('crm_create', section='bitrix', default=1))
    call_type = int(call_data.get('type', 1))

    crm_create = 0
    if crm_create_setting == 1:
        crm_create = 1
    elif crm_create_setting == 2 and call_type == 2:
        crm_create = 1
    elif crm_create_setting == 3 and call_type == 1:
        crm_create = 1

    show = 0
    if call_type == 1:
         show = int(get_param('show_card', default=1))

    payload = {
        'USER_ID': user_id,
        'PHONE_NUMBER': external,
        'CRM_CREATE': crm_create,
        'SHOW': show,
        'TYPE': call_type,
        'LINE_NUMBER': call_data.get('line_number', 'default'),
    }

    resp = call_bitrix('telephony.externalcall.register', payload)
    if not resp:
        return None
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
    call_bitrix('telephony.externalCall.attachRecord', payload)


def finish_call(call_data: dict, user_id=None):
    internal = call_data.get('internal')
    if not internal:
        user_id = get_param('default_user_id', section='bitrix', default='1')
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
    call_status = call_data.get('status') or 304
    payload = {
        'CALL_ID': call_id,
        'USER_ID': user_id,
        'USER_PHONE_INNER': internal,
        'DURATION': call_data.get('duration', 0),
        'STATUS_CODE': call_status
    }
    resp = call_bitrix('telephony.externalcall.finish', payload)
    if call_data.get('file_path') and (call_status == 200 or call_data.get('is_voicemail')):
        file_base64 = utils.get_file(call_data)
        if file_base64:
            upload_file(call_data, file_base64)
    return resp

def get_user_phone(user_id=None):
    conn = sqlite3.connect(APP_DB)
    
    if user_id:
        # Сначала ищем по user_id
        cur = conn.execute("SELECT user_phone, context FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if row and row[0] and row[1]:
            conn.close()
            return row[0], row[1]  # (user_phone, context)

        # Запрашиваем данные у Битрикса
        payload = {'ID': user_id}
        resp = call_bitrix('user.get', payload)
        if not resp:
            conn.close()
            return None
        resp.raise_for_status()
        user_data = resp.json().get('result', [])
        
        if user_data:
            user_phone = user_data[0].get('UF_PHONE_INNER')

            if user_phone:
                conn.execute(
                    '''
                    INSERT INTO users(user_phone, user_id)
                    VALUES (?, ?)
                    ON CONFLICT(user_phone) DO UPDATE SET user_id=excluded.user_id
                    ''',
                    (user_phone, user_id)
                )
                conn.commit()

                cur = conn.execute("SELECT user_phone, context FROM users WHERE user_phone = ?", (user_phone,))
                row = cur.fetchone()
                conn.close()
                if row and row[0] and row[1]:
                    return row[0], row[1]
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(ami_tools.update_peer_context(user_phone))
                except RuntimeError:
                    asyncio.run(ami_tools.update_peer_context(user_phone))
                return None

        conn.close()
        return None

    resp = call_bitrix('user.get', {"ACTIVE": True})
    if not resp:
        conn.close()
        return
    resp.raise_for_status()
    users = resp.json().get('result', [])
    for u in users:
        user_id = u.get('ID')
        user_phone = u.get('UF_PHONE_INNER', '')
        if user_id and user_phone:
            conn.execute(
                '''
                INSERT INTO users(user_phone, user_id)
                VALUES (?, ?)
                ON CONFLICT(user_phone) DO UPDATE SET user_id=excluded.user_id
                ''',
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
