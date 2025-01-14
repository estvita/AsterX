import os
import requests
import configparser
import logging

config = configparser.ConfigParser()
config.read('config.ini')

# Подключение к битрикс
B24_URL = config.get('bitrix', 'url')
CRM_CREATE = config.get('bitrix', 'crm_create')
SHOW_CARD = config.get('bitrix', 'show_card')
DEFAULT_PHONE = config.get('bitrix', 'default_phone')


logging.basicConfig(level=logging.INFO, format='%(message)s', filename='bitrix.log')
logger = logging.getLogger()

def register_call(call_data: dict):
    payload = {
        'USER_PHONE_INNER': call_data['internal'],
        'PHONE_NUMBER': call_data['external'],
        'CRM_CREATE': CRM_CREATE,
        'SHOW': SHOW_CARD,
        'TYPE': call_data['type']
    }

    resp = requests.post(f'{B24_URL}telephony.externalcall.register', json=payload)
    logger.info(f'register_call report: {resp.json()}')
    reg_data = resp.json()
    
    if 'error' in reg_data:
        error_description = reg_data.get('error_description')
        if error_description == 'USER_ID or USER_PHONE_INNER should be set':
            call_data['internal'] = DEFAULT_PHONE
            return register_call(call_data)

    if resp.status_code == 200:
        result = reg_data.get('result', {})
        call_id = result.get('CALL_ID')
        return call_id

    return None


def upload_file(call_data, file_base64):
    payload = {
        'CALL_ID': call_data['call_id'],
        'FILENAME': os.path.basename(call_data['file_path']),
        'FILE_CONTENT': file_base64
    }
    upload_file = requests.post(f'{B24_URL}telephony.externalCall.attachRecord', json=payload)
    logger.info(f'upload_file report: {upload_file.json()}')


def finish_call(call_data: dict, user_id=None):
    payload = {
        'CALL_ID': call_data['call_id'],
        'USER_ID': user_id,
        'USER_PHONE_INNER': call_data.get('internal'),
        'DURATION': call_data.get('duration', 0),
        'STATUS_CODE': call_data.get('status', 403)
    }

    resp = requests.post(f'{B24_URL}telephony.externalcall.finish', json=payload)
    finish_data = resp.json()
    logger.info(f'Call finish report: {finish_data}')

    # Проверяем наличие ошибки и необходимость повтора запроса
    if 'error' in finish_data:
        error_description = finish_data.get('error_description')
        if error_description == 'USER_ID or USER_PHONE_INNER should be set':
            call_data['internal'] = DEFAULT_PHONE
            return finish_call(call_data)

    return resp


def get_user_id(user_phone):
    payload = {
        'FILTER': {
            'UF_PHONE_INNER': user_phone
        }
    }

    resp = requests.post(f'{B24_URL}user.get', json=payload)
    if resp.status_code == 200:
        user_data = resp.json().get('result', {})
        return user_data[0].get('ID')
    else:
        return None
    

def get_user_phone(user_id):
    payload = {
        'ID': user_id
    }
    resp = requests.post(f'{B24_URL}user.get', json=payload)
    if resp.status_code == 200:
        user_data = resp.json().get('result', {})
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