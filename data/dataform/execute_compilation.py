"""Submit one Dataform invocation using a previously successful compilation."""
import json
import argparse
from pathlib import Path
from upload_workspace import request, base, PROJECT, root

parser=argparse.ArgumentParser()
parser.add_argument('--table',choices=['customers','products','transactions','complaints','branches','service_agents','daily_exchange_rates'],default='customers')
args=parser.parse_args()
path=root/'last_compilation.json'
state=json.loads(path.read_text(encoding='utf-8'))
if state.get('invocation'):
    raise SystemExit('This compilation was already submitted. Inspect its invocation first.')
result=request(base+'/workflowInvocations',{
    'compilationResult':state['compilationResult'],
    'invocationConfig':{
        'includedTags':[args.table],
        'transitiveDependenciesIncluded':True,
        'serviceAccount':f'bank-curation@{PROJECT}.iam.gserviceaccount.com'
    }
})
state['invocation']=result['name']
path.write_text(json.dumps(state,indent=2),encoding='utf-8')
print('INVOCATION:',result['name'])
print('RUN_ID:',state['run_id'])
print('STATE:',result.get('state','submitted'))
print(f'Inspect progress in https://console.cloud.google.com/dataform?project={PROJECT}')
