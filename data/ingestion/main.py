"""GCS -> contract -> staging -> reconciled raw publication -> audit."""
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

from google.api_core.exceptions import Conflict, PreconditionFailed
from google.cloud import bigquery, storage
from validation import ContractError, parse_contract, validate_csv


def now():
    return datetime.now(timezone.utc).isoformat()


def split_uri(uri):
    if not uri.startswith('gs://') or '/' not in uri[5:]:
        raise ValueError('Expected gs://bucket/object-or-prefix')
    return uri[5:].split('/', 1)


AUDIT_SCHEMA = [bigquery.SchemaField(name, kind) for name, kind in [
    ('event_id', 'STRING'), ('run_id', 'STRING'), ('event_time', 'TIMESTAMP'),
    ('table_name', 'STRING'), ('event', 'STRING'), ('status', 'STRING'),
    ('details_json', 'STRING')]]


class Pipeline:
    def __init__(self):
        self.project = os.environ['PROJECT_ID']
        self.location = os.environ['BQ_LOCATION']
        self.source = os.environ['SOURCE_URI']
        self.contract_uri = os.environ['CONTRACT_URI']
        self.target = os.environ['DESTINATION_TABLE']
        self.audit_dataset = os.environ.get('AUDIT_DATASET', 'bank_ops')
        if not re.fullmatch(r'[a-z0-9-]+\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*', self.target):
            raise ValueError('Invalid destination: use project.dataset.table')
        if not self.target.startswith(self.project + '.'):
            raise ValueError('Destination must belong to PROJECT_ID')
        self.run_id = uuid.uuid4().hex
        self.gcs = storage.Client(project=self.project)
        self.bq = bigquery.Client(project=self.project, location=self.location)
        self.ops = self.gcs.bucket(os.environ['OPS_BUCKET'])
        self.audit_table = f'{self.project}.{self.audit_dataset}.pipeline_events'
        self.stage = f'{self.project}.{self.audit_dataset}.stage_{self.run_id}'
        self.lock_generation = None
        self.published = False

    def job(self, create, job_id):
        # An ambiguous API retry attaches to the existing job, never appends twice.
        try:
            job = create(job_id)
        except Conflict:
            job = self.bq.get_job(job_id, location=self.location)
        job.result()
        return job

    def event(self, event, status, **details):
        event_id = uuid.uuid4().hex
        entry = dict(event_id=event_id, run_id=self.run_id, event_time=now(),
                     table_name=self.target, event=event, status=status,
                     details_json=json.dumps(details, ensure_ascii=False))
        print(json.dumps(dict(severity='ERROR' if status in ('FAILED', 'BLOCKED') else 'INFO',
                              **entry)), flush=True)
        # GCS is the durable fallback when BigQuery audit is unavailable.
        self.ops.blob(f'audit/{self.run_id}/{event_id}.json').upload_from_string(
            json.dumps(entry), content_type='application/json', if_generation_match=0)
        config = bigquery.LoadJobConfig(schema=AUDIT_SCHEMA,
            write_disposition='WRITE_APPEND', create_disposition='CREATE_NEVER')
        self.job(lambda ident: self.bq.load_table_from_json(
            [entry], self.audit_table, job_config=config, job_id=ident),
            f'audit_{event_id}')

    def execute(self):
        key = hashlib.sha256(self.target.encode()).hexdigest()
        self.lock = self.ops.blob(f'locks/{key}.json')
        try:
            self.lock.upload_from_string(json.dumps({'run_id': self.run_id,
                'destination': self.target, 'created_at': now(),
                'execution': os.environ.get('CLOUD_RUN_EXECUTION')}),
                if_generation_match=0)
            self.lock_generation = self.lock.generation
        except PreconditionFailed:
            self.event('run_finished', 'BLOCKED', reason='destination_locked')
            raise RuntimeError('Destination locked; inspect previous execution') from None

        try:
            self.event('run_started', 'RUNNING', source=self.source,
                       contract=self.contract_uri,
                       execution=os.environ.get('CLOUD_RUN_EXECUTION'),
                       revision=os.environ.get('PIPELINE_VERSION', '1.0.0'))
            bucket, name = split_uri(self.contract_uri)
            contract_blob = self.gcs.bucket(bucket).get_blob(name)
            if contract_blob is None:
                raise ValueError('Contract does not exist')
            raw_contract = contract_blob.download_as_bytes()
            contract, contract_hash = parse_contract(raw_contract)
            if contract['table'] != self.target.split('.')[-1]:
                raise ContractError('destination_table', {'reason': 'contract table mismatch'})
            self.ops.blob(f'audit/{self.run_id}/contract.json').upload_from_string(
                raw_contract, if_generation_match=0, content_type='application/json')

            bucket, name = split_uri(self.source)
            source_bucket = self.gcs.bucket(bucket)
            # Trailing slash means prefix. Every selected object must be CSV.
            objects = list(self.gcs.list_blobs(bucket, prefix=name)) if name.endswith('/') else [source_bucket.get_blob(name)]
            objects = [obj for obj in objects if obj and not obj.name.endswith('/')]
            objects.sort(key=lambda obj: obj.name)
            if not objects:
                raise ContractError('source_exists', {'objects': 0})
            if any(not obj.name.lower().endswith('.csv') for obj in objects):
                raise ContractError('source_format', {'required': 'uncompressed CSV only'})
            manifest = [dict(uri=f'gs://{bucket}/{obj.name}', generation=str(obj.generation),
                             size=obj.size, crc32c=obj.crc32c) for obj in objects]
            identity = dict(destination=self.target, contract_sha256=contract_hash, files=manifest)
            fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            self.ops.blob(f'audit/{self.run_id}/manifest.json').upload_from_string(
                json.dumps(identity), content_type='application/json', if_generation_match=0)
            self.event('manifest_recorded', 'PASSED', fingerprint=fingerprint,
                       contract_version=contract['version'], contract_sha256=contract_hash,
                       contract_generation=str(contract_blob.generation), objects=len(objects))

            total_rows = 0
            for index, obj in enumerate(objects):
                # Reading a pinned generation and copying that same generation avoids
                # validating one file revision but loading a later overwrite.
                try:
                    with obj.open('rt', encoding=contract['encoding'], newline='') as stream:
                        rows = validate_csv(stream, contract)
                except ContractError as exc:
                    exc.details.update(source_uri=f'gs://{bucket}/{obj.name}',
                                       generation=str(obj.generation))
                    raise
                source_bucket.copy_blob(obj, self.ops,
                    new_name=f'staging/{self.run_id}/{index:06d}.csv',
                    source_generation=obj.generation,
                    if_source_generation_match=obj.generation, if_generation_match=0)
                total_rows += rows
                print(json.dumps(dict(severity='INFO', run_id=self.run_id,
                    event='file_validated', file_index=index, rows=rows)), flush=True)
                manifest[index]['rows'] = rows

            if total_rows == 0:
                raise ContractError('non_empty_batch', {'rows': 0})
            self.ops.blob(f'audit/{self.run_id}/validation.json').upload_from_string(
                json.dumps({'files': manifest, 'total_rows': total_rows}),
                if_generation_match=0, content_type='application/json')
            self.event('structural_contract', 'PASSED', rows=total_rows, files=len(objects),
                       rules=['exact_header', 'column_count', 'csv_syntax', 'utf8', 'no_null_bytes', 'non_empty_batch'])

            schema = [bigquery.SchemaField(c, 'STRING', mode='NULLABLE') for c in contract['columns']]
            table = bigquery.Table(self.stage, schema=schema)
            table.expires = datetime.now(timezone.utc) + timedelta(days=2)
            self.bq.create_table(table)
            config = bigquery.LoadJobConfig(schema=schema, source_format='CSV',
                skip_leading_rows=1, field_delimiter=contract['delimiter'],
                quote_character=contract['quotechar'], encoding='UTF-8',
                allow_quoted_newlines=True, max_bad_records=0,
                write_disposition='WRITE_TRUNCATE', create_disposition='CREATE_NEVER')
            uri = f'gs://{self.ops.name}/staging/{self.run_id}/*.csv'
            load = self.job(lambda ident: self.bq.load_table_from_uri(
                uri, self.stage, job_config=config, job_id=ident), f'load_{self.run_id}')
            actual_rows = self.bq.get_table(self.stage).num_rows
            if actual_rows != total_rows:
                raise ContractError('row_reconciliation', {'expected': total_rows, 'actual': actual_rows})
            self.event('row_reconciliation', 'PASSED', source_rows=total_rows,
                       destination_rows=actual_rows, load_job_id=load.job_id)

            # The final table must not inherit the temporary table expiration.
            table = self.bq.get_table(self.stage)
            table.expires = None
            self.bq.update_table(table, ['expires'])
            copy = self.job(lambda ident: self.bq.copy_table(self.stage, self.target,
                job_config=bigquery.CopyJobConfig(write_disposition='WRITE_TRUNCATE'),
                job_id=ident), f'publish_{self.run_id}')
            self.published = True
            self.event('run_finished', 'SUCCEEDED', source_rows=total_rows,
                       destination_rows=actual_rows, load_job_id=load.job_id,
                       publication_job_id=copy.job_id, fingerprint=fingerprint)

        except Exception as exc:
            # Avoid logging exception messages that can contain CSV field values.
            details = dict(error_type=type(exc).__name__, published=self.published,
                           load_job_id=f'load_{self.run_id}', publication_job_id=f'publish_{self.run_id}')
            if isinstance(exc, ContractError):
                details.update(rule=exc.rule, rule_details=exc.details)
            try:
                self.event('run_finished', 'FAILED', **details)
            except Exception:
                print(json.dumps(dict(severity='CRITICAL', run_id=self.run_id,
                    event='audit_write_failed', **details)), flush=True)
            raise RuntimeError(f'Run {self.run_id} failed; inspect audit and BigQuery job IDs') from None
        finally:
            try:
                self.bq.delete_table(self.stage, not_found_ok=True)
            except Exception:
                print(json.dumps(dict(severity='WARNING', run_id=self.run_id,
                    event='staging_cleanup_failed', table=self.stage)), flush=True)
            if self.lock_generation is not None:
                self.lock.delete(if_generation_match=self.lock_generation)


if __name__ == '__main__':
    try:
        Pipeline().execute()
    except Exception as exc:
        print(json.dumps({'severity': 'ERROR', 'event': 'process_failed',
                          'error_type': type(exc).__name__}), flush=True)
        sys.exit(1)
