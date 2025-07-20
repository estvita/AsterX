import os
import sys
import base64
import fnmatch
import requests
from ftplib import FTP
from urllib.parse import urlparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

HOSTNAME = config.HOSTNAME
RECORD_URI = config.RECORD_URI
RECORD_USER = config.RECORD_USER
RECORD_PASS = config.RECORD_PASS
SSH_KEY = config.SSH_KEY
RECORD_PROTOCOL = config.RECORD_PROTOCOL


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
    

def load_private_key(filepath, password=None):
    import paramiko
    key_classes = [
        paramiko.RSAKey,
        paramiko.Ed25519Key,
        paramiko.ECDSAKey,
        paramiko.DSSKey
    ]
    for key_cls in key_classes:
        try:
            return key_cls.from_private_key_file(filepath, password=password)
        except Exception:
            continue
    raise ValueError(f"Не удалось определить тип ssh-ключа: {filepath}")

def download_file_sftp(remote_filepath):
    import paramiko
    if not SSH_KEY or not os.path.exists(SSH_KEY):
        print("Private key not found")
        return None

    try:
        transport = paramiko.Transport((HOSTNAME, 22))
    except Exception as e:
        print("Cannot connect to host:", e)
        return None

    private_key = load_private_key(SSH_KEY)
    try:
        transport.connect(username=RECORD_USER, pkey=private_key)
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.stat(remote_filepath)
        with sftp.open(remote_filepath, 'rb') as file_data:
            content = file_data.read()
    except FileNotFoundError:
        print(f"File not found: {remote_filepath}")
        content = None
    except Exception as e:
        print("SFTP error:", e)
        content = None
    finally:
        if 'sftp' in locals():
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


def get_file(call_data):
    file_path = call_data.get('file_path')
    if not file_path:
        return
    file_content = None
    if RECORD_PROTOCOL == "sftp":
        file_content = download_file_sftp(file_path)
    elif RECORD_PROTOCOL == "local":
        file_content = download_file_local(file_path)
    elif RECORD_PROTOCOL == "http":
        file_data = requests.get(file_path, auth=(RECORD_USER, RECORD_PASS))
        if file_data.status_code == 200:
            file_content = file_data.content
    if file_content:
        file_base64 = base64.b64encode(file_content).decode('utf-8')
        return file_base64
    return None