import os
import sys
import requests
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
import utils

# Подключение к битрикс
B24_URL = config.B24_URL
CRM_CREATE = config.CRM_CREATE
SHOW_CARD = config.SHOW_CARD
DEFAULT_USER_ID = config.DEFAULT_USER_ID


logging.basicConfig(level=logging.INFO, format='%(message)s', filename='bitrix.log')
logger = logging.getLogger()

def get_user_id(user_phone):
    payload = {
        'FILTER': {
            'UF_PHONE_INNER': user_phone
        }
    }
    try:
        resp = requests.post(f'{B24_URL}user.get', json=payload, timeout=10)
        resp_data = resp.json()
        logger.info(f'get_user_id report: {resp_data}')
        resp.raise_for_status()
        result = resp_data.get('result', [])
        if result:
            return result[0].get('ID')
        return DEFAULT_USER_ID
    except requests.exceptions.RequestException as e:
        logger.error(f'B24 request error: {e}')
        return None
    

def register_call(call_data: dict):
    internal = call_data.get('internal')
    if not internal:
        user_id = DEFAULT_USER_ID
    else:
        user_id = get_user_id(internal)
    if not user_id:
        return None

    payload = {
        'USER_ID': user_id,
        'PHONE_NUMBER': call_data['external'],
        'CRM_CREATE': CRM_CREATE,
        'SHOW': SHOW_CARD,
        'TYPE': call_data['type'],
    }
    resp = requests.post(f'{B24_URL}telephony.externalcall.register', json=payload)
    reg_data = resp.json()
    logger.info(f'register_call report: {reg_data}')
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
    upload_file = requests.post(f'{B24_URL}telephony.externalCall.attachRecord', json=payload)
    logger.info(f'upload_file report: {upload_file.json()}')


def finish_call(call_data: dict, user_id=None):
    internal = call_data.get('internal')
    if not internal:
        user_id = DEFAULT_USER_ID
    else:
        user_id = get_user_id(internal)
    if not user_id:
        return None
    call_id  = call_data.get('call_id')
    if not call_id:
        call_id = register_call(call_data)
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
    resp = requests.post(f'{B24_URL}telephony.externalcall.finish', json=payload)
    finish_data = resp.json()
    logger.info(f'Call finish report: {finish_data}')
    resp.raise_for_status()
    if call_status == 200:
        file_base64 = utils.get_file(call_data)
        if file_base64:
            upload_file(call_data, file_base64)

def get_user_phone(user_id):
    payload = {
        'ID': user_id
    }
    resp = requests.post(f'{B24_URL}user.get', json=payload)
    resp.raise_for_status()
    user_data = resp.json().get('result', [])
    if user_data:
        return user_data[0].get('UF_PHONE_INNER')
    else:
        return None

def card_action(call_id, user_phone, action):
    user_id = get_user_id(user_phone)
    if user_id:
        payload = {
            'CALL_ID': call_id,
            'USER_ID': user_id,
        }
        requests.post(f'{B24_URL}telephony.externalcall.{action}', json=payload)