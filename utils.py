import logging
import os
import redis
import requests
from urllib.parse import urlparse
import configparser
from ftplib import FTP
import fnmatch
import paramiko

config = configparser.ConfigParser()
config.read('config.ini')

HOSTNAME = config.get('asterisk', 'host')
RECORD_URI = config.get('asterisk', 'records_uri')
RECORD_USER = config.get('asterisk', 'record_user')
RECORD_PASS = config.get('asterisk', 'record_pass')
KEY = config.get('asterisk', 'key_filepath')

r = redis.Redis(host='localhost', port=6379, db=1)

def setup_logger(linked_id):
    log_dir = 'events'
    log_filename = f'{log_dir}/{linked_id}.txt'
    
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    if r.exists(f'logger:{linked_id}'):
        logger = logging.getLogger(linked_id)
    else:
        logger = logging.getLogger(linked_id)
        logger.setLevel(logging.INFO)
        
        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')
        file_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        
        r.set(f'logger:{linked_id}', log_filename)
    
    return logger


def ftp_download(partial_file_name: str, directory: str) -> bytes:
    parsed_url = urlparse(RECORD_URI)
    ftp = FTP(parsed_url.hostname)
    ftp.login(RECORD_USER, RECORD_PASS)

    full_path = os.path.join(parsed_url.path, directory)
    ftp.cwd(full_path)

    files = ftp.nlst()

    matching_files = fnmatch.filter(files, f'*{partial_file_name}*')

    if not matching_files:
        print(f"Файл с частью имени '{partial_file_name}' не найден.")
        ftp.quit()
        return None

    file_name = matching_files[0]
    file_content = bytearray()

    def handle_binary(more_data):
        file_content.extend(more_data)

    try:
        ftp.retrbinary(f'RETR {file_name}', callback=handle_binary)
    except Exception as e:
        print(f"Ошибка при скачивании файла: {e}")
        ftp.quit()
        return None

    ftp.quit()
    
    return bytes(file_content), file_name


def http_download(file_path: str) -> bytes:
    file_data = requests.get(f'{RECORD_URI}{file_path}', auth=(RECORD_USER, RECORD_PASS))
    if file_data.status_code == 200:
        return file_data.content
    else:
        return None
    

def download_file_sftp(remote_filepath):
    transport = paramiko.Transport((HOSTNAME, 22))
    private_key = paramiko.RSAKey.from_private_key_file(KEY)
    transport.connect(username=RECORD_USER, pkey=private_key)
    sftp = paramiko.SFTPClient.from_transport(transport)
    
    try:
        sftp.stat(remote_filepath)
        
        with sftp.open(remote_filepath, 'rb') as file_data:
            content = file_data.read()
    except FileNotFoundError:
        print(f"File not found: {remote_filepath}")
        content = None
    finally:
        sftp.close()
        transport.close()
    
    return content


def download_file_local(filepath):
    try:
        with open(filepath, 'rb') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        content = None
    return content