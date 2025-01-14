+ [Enable API](https://help.yeastar.com/en/s-series-developer/api/enable_api_access_on_pbx.html)
+ Login and password enter in config.ini section yeastar
+ end_port - endpoint port for receiving webhooks from PBX (the server on which this integration is running)
+ upd_period = 1500 - token confirmation period, up to 30 min. (https://help.yeastar.com/en/s-series-developer-v2/api-v2/heartbeat.html)
+ Run [app.py](app.py), the token will be received automatically and written to Redis


```
#config.ini
[yeastar]
api_url = http://192.168.1.10:8088/api/v2.0.0/
api_user = pbx
api_pass = pass
upd_period = 1500
end_port = 8000
```