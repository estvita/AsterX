# AsterX Синхронизация звонков с Битрикс24 через ARI, AMI или API (Yeastar)

https://github.com/estvita/AsterX

Протестировано с Asterisk v. 16, 18, 20 (FreePBX), [Yeastar](/yeastar/) S50

Скрипт позволяет отправлять историю звонков и файлы записей из Asterisk (FreePBX) в Битрикс24

## Настройка на стороне Битрикс24
+ Входящий вебхук с правами: crm, user, telephony. Интеграции > Rest API > Другое > Входящий вебхук
+ Исходящий вебхук для событий ONEXTERNALCALLSTART, ONEXTERNALCALLBACKSTART. В поле "URL вашего обработчика" ввести адрес http://X.X.X.X:8000/asterx

### Установка 

Для временного хранения информации о звонках используется:
+ [Redis Stack](https://redis.io/docs/latest/operate/oss_and_stack/install/archive/install-stack/) 
+ или SQLite


```
cd /opt
git clone https://github.com/estvita/asterx.git
cd asterx
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp examples/config.ini config.ini
nano config.ini
```
 
### Заполнить данные в [config.ini](examples/config.ini)

[app]
+ [debug] - Режим отладки (True/False)
+ [port] - Порт запуска приложения 8000
+ [engine] - ami_reis (по умолчанию), ami_sql или ari для подключения к Asterisk
+ [logging] - True/False - включить/отключить запись получаемых событий в файл.

[bitrix]
+ [url] - Адрес воходящего вебхука.
+ [token] - Выдаётся Битриксом при создании исходящего вебхука
+ [crm_create] - Создавать или нет сущность CRM. 0 - не создавать, 1 - всегда создавать, 2 - только для входящих звонков, 3 - только для исходящих
+ [show_card] - 0 (не показывать карточку), 1 (во время вызова), 2 (при поднятии трубки)
+ [default_user_id] - Потерянные входящие звонки регистрируются на этого пользователя (по умолчанию 1).

[asterisk]
+ [ws_type] - wss/ws - требуестя при подключении к ARI
+ [host] - адрес ATC (localhost - по умолчанию)
+ [port] - AMI/ARI порт
+ [username] - AMI/ARI пользователь
+ [secret] - AMI/ARI пароль
+ [records_protocol] sftp, http или local
+ [key_filepath] - ssh ключ для sftp
+ [records_uri] - url с записями звонков с HTTP Basic Auth (https://example.com/monitor/). Пример конфига [Apache](examples/monitor.conf)  
+ [record_user] - логин Basic Auth
+ [record_pass] - пароль Basic Auth
+ [internal_contexts] - список контекстов внутренних (исходящие) вызовов. По умолчанию "from-internal"
+ [external_contexts] - список контекстов для входящих вызовов. По умолчанию "from-pstn"

## Запуск интеграции
```
cd /opt/asterx
source .venv/bin/activate

+ ARI/AMI: python main.py
+ Получение событий: gunicorn --bind 0.0.0.0:8000 wsgi:app
+ Yeastar API: python yeastar/app.py

```

## Автоматический запуск 
Пример конфигурации [systemd](/examples/asterx.service) для автоматического запуска

```
cp /opt/asterx/examples/asterx.service /etc/systemd/system/asterx.service
systemctl enable asterx.service
systemctl start asterx.service
```
