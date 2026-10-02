"""Read-only GCP inventory; GET requests only, no SQL jobs or deployments."""
import base64, hashlib, json, subprocess, urllib.request, urllib.parse, urllib.error
from pathlib import Path
from datetime import datetime, timezone
import zipfile

PROJECT='hackaton-509923'
REGION='us-central1'
TABLES=['customers','products','transactions','complaints','branches','service_agents','daily_exchange_rates']
SAFE_ENV={'PROJECT_ID','BQ_LOCATION','OPS_BUCKET','AUDIT_DATASET','SOURCE_URI','CONTRACT_URI','DESTINATION_TABLE','PIPELINE_VERSION'}

def digest(data):
    return hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()

def main():
    baseline=json.loads(Path(__file__).with_name('audit_baseline.json').read_text())
    out=Path('gcp-audit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    token=subprocess.check_output(['gcloud','auth','print-access-token'],text=True).strip()
    errors=[]
    def get(url,params=None,binary=False):
        if params: url+='?'+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token},method='GET')
        try:
            with urllib.request.urlopen(req,timeout=90) as resp:
                data=resp.read()
            return data if binary else json.loads(data)
        except urllib.error.HTTPError as e:
            errors.append({'resource':url.split('?')[0],'http_status':e.code})
        except (urllib.error.URLError,TimeoutError):
            errors.append({'resource':url.split('?')[0],'error':'network_or_timeout'})
        return None
    def pages(url,key,params=None):
        params=dict(params or {})
        result=[]
        while True:
            page=get(url,params)
            if page is None: return result
            result.extend(page.get(key,[]))
            if not page.get('nextPageToken'): return result
            params['pageToken']=page['nextPageToken']
    report={'project':PROJECT,'collected_at':datetime.now(timezone.utc).isoformat(),
            'limits':['No effective IAM check','No SQL or row reads','Workspace comparison does not prove deployed compilation parity','Non-atomic cloud snapshot'],
            'dataform':[],'jobs':[],'contracts':[],'tables':[]}
    repo=f'https://dataform.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/repositories/bank-transformations'
    metadata=get(repo)
    if metadata:
        report['repository']={'name':metadata.get('name'),'serviceAccount':metadata.get('serviceAccount'),
         'gitRemoteConfigured':bool(metadata.get('gitRemoteSettings'))}
    ws=repo+'/workspaces/development'
    for name,sha in baseline['dataform'].items():
        result=get(ws+':readFile',{'path':name})
        if result is None:
            report['dataform'].append({'path':name,'state':'UNREADABLE'}); continue
        cloud=digest(base64.b64decode(result['fileContents']))
        report['dataform'].append({'path':name,'state':'MATCH' if cloud==sha else 'DIFFERENT','local_sha256':sha,'cloud_sha256':cloud})
    # Inventory root/directories including remote-only files without downloading them.
    report['workspace_directory_entries']={}
    for directory in ['', 'definitions','includes']:
        report['workspace_directory_entries'][directory]=pages(ws+':queryDirectoryContents','directoryEntries',{'path':directory,'pageSize':100})
    inv=get(repo+'/workflowInvocations',{'pageSize':20})
    if inv:
        report['recent_invocations']=[{k:i.get(k) for k in ['name','state','compilationResult','resolvedCompilationResult','invocationTiming']} for i in inv.get('workflowInvocations',[])]
    jobs=pages(f'https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs','jobs')
    for job in jobs:
        if not job.get('name','').split('/')[-1].startswith('bank-ingestion-'):continue
        template=job.get('template',{})
        task=template.get('template',{})
        containers=[]
        for container in task.get('containers',[]):
            containers.append({'image':container.get('image'),'resources':container.get('resources'),
             'env':{e['name']:e.get('value','<secret_reference>') for e in container.get('env',[]) if e.get('name') in SAFE_ENV}})
        report['jobs'].append({'name':job.get('name'),'serviceAccount':task.get('serviceAccount'),
          'timeout':task.get('timeout'),'maxRetries':task.get('maxRetries'),
          'taskCount':template.get('taskCount'),'parallelism':template.get('parallelism'),'containers':containers,
          'latestCreatedExecution':job.get('latestCreatedExecution')})
    for bucket in ['factoredia_hackaton',PROJECT+'-ingestion-ops']:
        meta=get('https://storage.googleapis.com/storage/v1/b/'+bucket)
        if meta:report.setdefault('buckets',[]).append({k:meta.get(k) for k in ['name','location','versioning','lifecycle','iamConfiguration']})
    bucket='factoredia_hackaton'
    objects=pages(f'https://storage.googleapis.com/storage/v1/b/{bucket}/o','items',{'prefix':'contracts/'})
    for obj in objects:
        name=obj['name']
        if not name.endswith('.json'):continue
        content=get(f'https://storage.googleapis.com/storage/v1/b/{bucket}/o/'+urllib.parse.quote(name,safe=''),{'alt':'media','generation':obj['generation']},binary=True)
        if content is None:continue
        try:c=json.loads(content)
        except ValueError:
            report['contracts'].append({'name':name,'state':'INVALID_JSON'});continue
        # Export only the known structural contract fields, never arbitrary contents.
        allowed=['version','table','columns','raw_type','nullable','encoding','delimiter','quotechar']
        sanitized={k:c[k] for k in allowed if k in c}
        path=out/'contracts'/Path(name).name;path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(sanitized,indent=2),encoding='utf-8')
        local=baseline['contracts'].get(Path(name).name)
        report['contracts'].append({'name':name,'generation':obj['generation'],'sha256':digest(content),
          'state':'MISSING_LOCALLY' if local is None else 'MATCH' if local==sanitized else 'DIFFERENT',
          'export':'structural_fields_only'})
    for dataset in ['bank_raw','bank_curated','bank_ops','bank_stage','bank_quarantine']:
        url=f'https://bigquery.googleapis.com/bigquery/v2/projects/{PROJECT}/datasets/{dataset}'
        meta=get(url)
        if meta:report.setdefault('datasets',[]).append({'dataset':dataset,'location':meta.get('location')})
        if dataset not in ['bank_raw','bank_curated']:continue
        for table in TABLES:
            meta=get(url+'/tables/'+table)
            if meta:report['tables'].append({'dataset':dataset,'table':table,**{k:meta.get(k) for k in ['schema','numRows','location','timePartitioning','clustering','lastModifiedTime']}})
    report['errors']=errors
    report['collection_status']='PARTIAL' if errors else 'COLLECTED_NOT_CERTIFIED'
    (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    with zipfile.ZipFile(str(out)+'.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(out))
    print('RESULT:',str(out)+'.zip')
    print('STATUS:',report['collection_status'])
    print('Dataform:',{state:sum(x['state']==state for x in report['dataform']) for state in ['MATCH','DIFFERENT','UNREADABLE']})
    print('Read errors:',len(errors))

if __name__=='__main__':main()
