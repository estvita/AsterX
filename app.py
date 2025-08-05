import sys
import asyncio
import importlib
from flask import Flask, request, jsonify

import bitrix
import ami_tools
import project
import config

engine_name = config.ENGINE

try:
    engine_module = importlib.import_module(engine_name)
except ImportError as e:
    sys.exit(f"Failed to import module '{engine_name}': {e}")

app = Flask(__name__)

print(config.TOKEN)

@app.route('/', methods=['GET', 'POST'])
def project_info():
    return jsonify(project.data)  
    
@app.route('/asterx', methods=['POST'])
async def b24_handler():
    application_token = request.form.get('auth[application_token]')
    if application_token != config.TOKEN:
        return 'Error', 403
    
    event = request.form.get('event')

    if event == 'ONEXTERNALCALLSTART':
        user_id = request.form.get('data[USER_ID]')
        call_id = request.form.get('data[CALL_ID]')
        external = request.form.get('data[PHONE_NUMBER]')
        endpoint = bitrix.get_user_phone(user_id)
        if endpoint:
            internal, context = endpoint
            await ami_tools.originate(internal, context, external, call_id)

        else:
            bitrix.finish_call({'call_id': call_id}, user_id)

    elif event == 'ONEXTERNALCALLBACKSTART':
        external = request.form.get('data[PHONE_NUMBER]')
        try:
            resp = bitrix.call_bitrix('telephony.externalCall.searchCrmEntities', {'PHONE_NUMBER': external})
            if resp:
                result = resp.json().get('result', [])
                assigned_by = result[0].get('ASSIGNED_BY', {})
                user_id = assigned_by.get('ID')
                endpoint = bitrix.get_user_phone(user_id)
                if endpoint:
                    internal, context = endpoint
                    payload = {
                        'external': external,
                        'type': 4
                    }
                    call_id = bitrix.register_call(payload, user_id)
                    await ami_tools.originate(internal, context, external, call_id)
        except Exception as e:
            print(event, f"Error: {e}")

    return 'event processed'
    

if __name__ == '__main__':
  
    app.run(debug=config.APP_DEBUG, host='0.0.0.0', port=config.APP_PORT, use_reloader=False)