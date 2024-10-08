import logging
import os
import redis
import requests
from urllib.parse import urlparse
import configparser
from ftplib import FTP
import fnmatch

config = configparser.ConfigParser()
config.read('config.ini')

RECORD_URL = config.get('asterisk', 'records_url')
RECORD_USER = config.get('asterisk', 'record_user')
RECORD_PASS = config.get('asterisk', 'record_pass')

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
    parsed_url = urlparse(RECORD_URL)
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
    file_data = requests.get(f'{RECORD_URL}{file_path}', auth=(RECORD_USER, RECORD_PASS))
    if file_data.status_code == 200:
        return file_data.content
    else:
        return None