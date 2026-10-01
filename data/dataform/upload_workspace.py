"""Upload source files to an existing Dataform workspace; never executes SQL."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import urllib.error
import uuid

PROJECT = 'hackaton-509923'
REGION = 'us-central1'
REPOSITORY = 'bank-transformations'
WORKSPACE = 'development'
base = f'https://dataform.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/repositories/{REPOSITORY}'
root = Path(__file__).resolve().parent
run_id = 'r_' + uuid.uuid4().hex


def request(url, data=None):
    # Token is obtained at runtime and never saved or printed.
    token = subprocess.check_output(['gcloud','auth','print-access-token'],text=True).strip()
    req = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(),
        headers={'Authorization':'Bearer '+token, 'Content-Type':'application/json'},
        method='GET' if data is None else 'POST')
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            payload=response.read()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as error:
        print(error.read().decode(), file=sys.stderr)
        raise SystemExit(f'Dataform HTTP {error.code}') from None


if __name__ == '__main__':
    # These must exist already. Avoid silently creating a repo with unknown identity.
    request(base + '/workspaces/' + WORKSPACE)
    files = [root/'workflow_settings.yaml', root/'package.json']
    files += sorted((root/'includes').glob('*.js'))
    files += sorted((root/'definitions').glob('*.js'))
    for file in files:
        relative = file.relative_to(root).as_posix()
        body = file.read_bytes()
        request(base+'/workspaces/'+WORKSPACE+':writeFile',
                {'path':relative,'contents':base64.b64encode(body).decode()})
        print('Uploaded:',relative)
    print('Installing Dataform dependencies in the workspace...')
    request(base+'/workspaces/'+WORKSPACE+':installNpmPackages', {})
    result=request(base+'/compilationResults', {
        'workspace':f'projects/{PROJECT}/locations/{REGION}/repositories/{REPOSITORY}/workspaces/{WORKSPACE}',
        'codeCompilationConfig':{'vars':{'run_id':run_id}}})
    if result.get('compilationErrors'):
        print(json.dumps(result['compilationErrors'],indent=2))
        raise SystemExit('Compilation failed; no workflow executed.')
    print('COMPILED:',result['name'])
    print('RUN_ID:',run_id)
    print('No SQL executed. Keep the compilation name to run this version through the API.')
    (root/'last_compilation.json').write_text(json.dumps({
        'compilationResult':result['name'], 'run_id':run_id},indent=2),encoding='utf-8')
