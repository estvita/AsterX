import configparser

config_file = 'config.ini'
config = configparser.ConfigParser()
config.read(config_file)

ENGINE = config.get('app', 'engine', fallback="ami_redis")
REDIS_DB = config.get('app', 'redis_db', fallback=1)

B24_URL = config.get('bitrix', 'url')
CRM_CREATE = config.get('bitrix', 'crm_create', fallback=0)
SHOW_CARD = config.get('bitrix', 'show_card', fallback=1)
DEFAULT_USER_ID = config.get('bitrix', 'default_user_id', fallback=1)

HOSTNAME = config.get('asterisk', 'host', fallback='localhost')
RECORD_PROTOCOL = config.get('asterisk', 'records_protocol', fallback='local')
RECORD_URI = config.get('asterisk', 'records_uri', fallback=0)
RECORD_USER = config.get('asterisk', 'record_user', fallback=0)
RECORD_PASS = config.get('asterisk', 'record_pass', fallback=0)
SSH_KEY = config.get('asterisk', 'key_filepath', fallback=0)
LOGGING = config.getboolean('asterisk', 'logging', fallback=0)
EXTERNAL_CONTEXTS = [s.strip() for s in config.get('asterisk', 'external_contexts', fallback='from-pstn').split(',')]
INTERNAL_CONTEXTS = [s.strip() for s in config.get('asterisk', 'internal_contexts', fallback='from-internal').split(',')]