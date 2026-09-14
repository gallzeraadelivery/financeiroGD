import json, subprocess, urllib.request
container=json.loads(subprocess.check_output(['docker','inspect','evolution-api-5wzr-api-1']))[0]
env=dict(item.split('=',1) for item in container['Config']['Env'])
key=env.get('AUTHENTICATION_API_KEY','')
request=urllib.request.Request('http://127.0.0.1:32769/instance/fetchInstances',headers={'apikey':key})
data=json.load(urllib.request.urlopen(request,timeout=20))
for item in data:
    print(json.dumps({k:item.get(k) for k in ['name','connectionStatus','ownerJid']},ensure_ascii=False))
