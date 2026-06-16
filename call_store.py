import json

import redis

import config


CALL_TTL = 12 * 60 * 60
KEY_PREFIX = "asterx:call:"

r = redis.Redis(host="localhost", port=6379, db=int(config.REDIS_DB), decode_responses=True)


def _key(linked_id):
    return f"{KEY_PREFIX}{linked_id}"


def get_call_data(linked_id):
    raw = r.get(_key(linked_id))
    if not raw:
        return None
    return json.loads(raw)


def update_call_data(linked_id, **kwargs):
    call_data = get_call_data(linked_id) or {"linked_id": linked_id}
    call_data.update(kwargs)
    r.set(_key(linked_id), json.dumps(call_data), ex=CALL_TTL)
    return call_data


def delete_call_data(linked_id):
    r.delete(_key(linked_id))
