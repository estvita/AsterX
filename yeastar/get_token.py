import configparser
import hashlib
import requests
import redis
# Коннект к Redis
r = redis.Redis(host='localhost', port=6379, db=0)

config = configparser.ConfigParser()
config.read('config.ini')

API_USER = config.get('yeastar', 'api_user')
API_PASS = config.get('yeastar', 'api_pass')
API_URL = config.get('yeastar', 'api_url')
EDPOINT_PORT = config.get('yeastar', 'end_port')

def get_token():

    md5_hash = hashlib.md5(API_PASS.encode()).hexdigest()

    payload = {
        'username': API_USER,
        'password': md5_hash,
        'port': EDPOINT_PORT,
        'url': 'yeastar'
    }

    resp = requests.post(f'{API_URL}login', json=payload).json()

    if resp.get('status') == 'Success':
        token = resp.get('token')
        r.set('yeastar_token', token)
        return token
    else:
        return None


def send_heartbeat():
    token = r.get('yeastar_token')
    if not token:
        print("Token not found, requesting new token...")
        token = get_token()
    else:
        token = token.decode('utf-8')

    try:
        resp = requests.post(f'{API_URL}heartbeat?token={token}').json()
        if resp.get('status') == 'Failed':
            print("Heartbeat failed:", resp)
            token = get_token()
        else:
            print("Heartbeat succeeded.")
    except requests.exceptions.RequestException as e:
        print("Error during heartbeat request:", str(e))