+ [Включить API ](https://help.yeastar.com/en/s-series-developer/api/enable_api_access_on_pbx.html)
+ Логин и пароль вписать в config.ini секция yeastar
+ end_port - порт конечной точки для приема вехуков из АТС (сервер на котором запущена эта интеграция)
+ upd_period = 1500 - период подтверждения токена, до 30 имн. (https://help.yeastar.com/en/s-series-developer-v2/api-v2/heartbeat.html)
+ Запустить [app.py](app.py), токен будет получен автоматически и записан в Redis


```
#config.ini
[yeastar]
api_url = http://192.168.1.10:8088/api/v2.0.0/
api_user = pbx
api_pass = pass
upd_period = 1500
end_port = 8000
```