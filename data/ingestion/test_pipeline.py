"""Control-flow tests with simulated cloud clients; no credentials or network."""
import importlib.util
import io
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def load_pipeline():
    modules = {name: types.ModuleType(name) for name in (
        'google', 'google.api_core', 'google.api_core.exceptions',
        'google.cloud', 'google.cloud.storage', 'google.cloud.bigquery')}
    exceptions = modules['google.api_core.exceptions']
    exceptions.Conflict = type('Conflict', (Exception,), {})
    exceptions.PreconditionFailed = type('PreconditionFailed', (Exception,), {})
    bq = modules['google.cloud.bigquery']
    for name in ('SchemaField', 'LoadJobConfig', 'CopyJobConfig', 'Table'):
        setattr(bq, name, MagicMock())
    modules['google.cloud'].bigquery = bq
    modules['google.cloud'].storage = modules['google.cloud.storage']
    spec = importlib.util.spec_from_file_location('pipeline_under_test', Path(__file__).with_name('main.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.module = load_pipeline()
        self.p = self.module.Pipeline.__new__(self.module.Pipeline)
        p = self.p
        p.project, p.location = 'test-project', 'us-central1'
        p.target, p.stage = 'test-project.bank_raw.customers', 'test-project.bank_ops.stage_test'
        p.run_id, p.published, p.lock_generation = 'test', False, None
        p.source, p.contract_uri = 'gs://source/data/customers.csv', 'gs://source/contracts/customers.json'
        p.gcs, p.bq, p.ops, p.event = MagicMock(), MagicMock(), MagicMock(), MagicMock()
        p.ops.name = 'ops'
        self.blob = MagicMock(name='source_blob')
        self.blob.name, self.blob.generation = 'data/customers.csv', 123
        self.blob.size, self.blob.crc32c = 20, 'checksum'
        self.blob.open.return_value = io.StringIO('customer_id\n001\n')
        contract = dict(version='1', table='customers', columns=['customer_id'],
                        encoding='utf-8-sig', delimiter=',', quotechar='"',
                        raw_type='STRING', nullable=True)
        cb = MagicMock()
        cb.download_as_bytes.return_value = json.dumps(contract).encode()
        cb.generation = 456
        self.bucket = p.gcs.bucket.return_value
        self.bucket.get_blob.side_effect = [cb, self.blob]
        p.bq.get_table.return_value.num_rows = 1

    def test_success_reconciles_then_publishes(self):
        self.p.execute()
        self.p.bq.copy_table.assert_called_once()
        self.assertTrue(self.p.published)
        self.assertEqual(self.p.event.call_args.args, ('run_finished', 'SUCCEEDED'))
        kwargs = self.bucket.copy_blob.call_args.kwargs
        self.assertEqual(kwargs['source_generation'], 123)
        self.assertEqual(kwargs['if_source_generation_match'], 123)

    def test_invalid_header_never_loads_or_publishes(self):
        self.blob.open.return_value = io.StringIO('wrong\n001\n')
        with self.assertRaises(RuntimeError):
            self.p.execute()
        self.p.bq.load_table_from_uri.assert_not_called()
        self.p.bq.copy_table.assert_not_called()
        self.assertEqual(self.p.event.call_args.kwargs['rule'], 'header')

    def test_count_mismatch_never_publishes(self):
        self.p.bq.get_table.return_value.num_rows = 2
        with self.assertRaises(RuntimeError):
            self.p.execute()
        self.p.bq.copy_table.assert_not_called()
        self.assertEqual(self.p.event.call_args.kwargs['rule'], 'row_reconciliation')

    def test_existing_lock_blocks_run(self):
        self.p.ops.blob.return_value.upload_from_string.side_effect = self.module.PreconditionFailed()
        with self.assertRaises(RuntimeError):
            self.p.execute()
        self.p.bq.copy_table.assert_not_called()
        self.assertEqual(self.p.event.call_args.args, ('run_finished', 'BLOCKED'))

    def test_api_conflict_reuses_job(self):
        create = MagicMock(side_effect=self.module.Conflict())
        self.p.job(create, 'stable_job_id')
        self.p.bq.get_job.assert_called_once_with('stable_job_id', location='us-central1')
        self.p.bq.get_job.return_value.result.assert_called_once()


if __name__ == '__main__':
    unittest.main()
