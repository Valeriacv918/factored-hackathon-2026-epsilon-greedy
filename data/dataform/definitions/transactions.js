const C = require('includes/transactions_contract');
const H = require('includes/transactions_helpers');
const P = dataform.projectConfig.defaultDatabase;
const run = dataform.projectConfig.vars.run_id;
if(!/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(run || '')) throw Error('run_id must be a letter followed by <=63 letters, digits or underscores');
const name = base => `${base}_${run}`;
const config = {schema:'bank_stage', tags:['transactions'], bigquery:{additionalOptions:{expiration_timestamp:'TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)'}}};
const ref = (ctx, base) => ctx.ref('bank_stage',name(base));
const runs = '`'+P+'.bank_ops.curation_runs`';
const audit = '`'+P+'.bank_ops.curation_results`';
const rejected = '`'+P+'.bank_quarantine.transactions_rejected`';
const columns = C.fields.map(f=>f.name).join(', ');

declare({database:P,schema:'bank_raw',name:'transactions'});

operate(name('transactions_input')).config({schema:'bank_stage',hasOutput:true,tags:['transactions']}).queries(ctx=>`
DECLARE snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP();
ASSERT '${run}' != 'preview' AS 'Set a fresh run_id before execution';
CREATE TABLE IF NOT EXISTS ${runs} (
  run_id STRING, table_name STRING, contract_version STRING, contract_json STRING,
  source_snapshot_at TIMESTAMP, started_at TIMESTAMP, finished_at TIMESTAMP,
  status STRING, input_rows INT64, published_rows INT64, pending_rules ARRAY<STRING>
) PARTITION BY DATE(started_at) OPTIONS(partition_expiration_days=30);
CREATE TABLE IF NOT EXISTS ${audit} (
  run_id STRING, recorded_at TIMESTAMP, rule_id STRING, observed INT64,
  expected INT64, passed BOOL, severity STRING
) PARTITION BY DATE(recorded_at) OPTIONS(partition_expiration_days=30);
ASSERT NOT EXISTS(SELECT 1 FROM ${runs} WHERE run_id='${run}' AND table_name='transactions') AS 'run_id already exists; use a fresh ID';
INSERT INTO ${runs} VALUES('${run}','transactions','${C.version}',${H.lit(JSON.stringify(C))},snapshot_at,
  CURRENT_TIMESTAMP(),NULL,'RUNNING',NULL,NULL,[${H.list(C.pendingRules)}]);
BEGIN
  CREATE TABLE ${ctx.self()}
  OPTIONS(expiration_timestamp=TIMESTAMP_ADD(CURRENT_TIMESTAMP(),INTERVAL 7 DAY)) AS
  SELECT r.*, snapshot_at AS _source_snapshot_at
  FROM ${ctx.ref('bank_raw','transactions')} AS r FOR SYSTEM_TIME AS OF snapshot_at;
  CREATE TABLE \`${P}.bank_stage.transactions_customers_${run}\`
  OPTIONS(expiration_timestamp=TIMESTAMP_ADD(CURRENT_TIMESTAMP(),INTERVAL 7 DAY)) AS
  SELECT customer_id, _curation_run_id FROM \`${P}.bank_curated.customers\`
  FOR SYSTEM_TIME AS OF snapshot_at;
  ASSERT (SELECT COUNT(*) FROM \`${P}.bank_stage.transactions_customers_${run}\`)>0
    AS 'Published customers reference is empty';
  CREATE TABLE \`${P}.bank_stage.transactions_products_${run}\`
  OPTIONS(expiration_timestamp=TIMESTAMP_ADD(CURRENT_TIMESTAMP(),INTERVAL 7 DAY)) AS
  SELECT product_id,customer_id,currency,_curation_run_id
  FROM \`${P}.bank_curated.products\` FOR SYSTEM_TIME AS OF snapshot_at;
  ASSERT (SELECT COUNT(*)>0 AND COUNT(*)=COUNT(DISTINCT product_id)
    AND COUNT(DISTINCT _curation_run_id)=1 FROM \`${P}.bank_stage.transactions_products_${run}\`)
    AS 'Products reference must be nonempty, unique and from one run';
  ASSERT (SELECT COUNT(*)=COUNT(DISTINCT customer_id)
    AND COUNT(DISTINCT _curation_run_id)=1 FROM \`${P}.bank_stage.transactions_customers_${run}\`)
    AS 'Customers reference must be unique and from one run';
  CREATE TABLE \`${P}.bank_stage.transactions_parent_quarantine_${run}\`
  OPTIONS(expiration_timestamp=TIMESTAMP_ADD(CURRENT_TIMESTAMP(),INTERVAL 7 DAY)) AS
  SELECT DISTINCT NULLIF(TRIM(JSON_VALUE(raw_json,'$.product_id')),'') AS product_id
  FROM \`${P}.bank_quarantine.products_rejected\` FOR SYSTEM_TIME AS OF snapshot_at
  WHERE run_id IN (SELECT _curation_run_id FROM \`${P}.bank_stage.transactions_products_${run}\`);
  CREATE TABLE IF NOT EXISTS \`${P}.bank_ops.curation_references\` (
    run_id STRING,recorded_at TIMESTAMP,reference_table STRING,
    reference_run_id STRING,source_snapshot_at TIMESTAMP
  ) PARTITION BY DATE(recorded_at) OPTIONS(partition_expiration_days=30);
  INSERT INTO \`${P}.bank_ops.curation_references\`
  SELECT DISTINCT '${run}',CURRENT_TIMESTAMP(),'customers',_curation_run_id,snapshot_at
  FROM \`${P}.bank_stage.transactions_customers_${run}\`
  UNION ALL
  SELECT DISTINCT '${run}',CURRENT_TIMESTAMP(),'products',_curation_run_id,snapshot_at
  FROM \`${P}.bank_stage.transactions_products_${run}\`;
  UPDATE ${runs} SET input_rows=(SELECT COUNT(*) FROM ${ctx.self()}) WHERE run_id='${run}' AND table_name='transactions';
EXCEPTION WHEN ERROR THEN
  UPDATE ${runs} SET status='FAILED',finished_at=CURRENT_TIMESTAMP() WHERE run_id='${run}' AND table_name='transactions';
  RAISE;
END;
`);

publish(name('transactions_typed'),{...config,type:'table'}).query(ctx=>`
WITH normalized AS (
  SELECT ${C.fields.map(f=>`${H.normalized(f,C)} AS ${f.name}`).join(',\n')},
    TO_JSON_STRING(STRUCT(${C.fields.map(f=>`r.${f.name}`).join(',')})) AS _raw_json,
    _source_snapshot_at
  FROM ${ref(ctx,'transactions_input')} r
)
SELECT ${C.fields.map(f=>`${H.typed(f,C)} AS ${f.name}`).join(',\n')},
  ${H.errors(C)} AS _errors,
  _raw_json, TO_HEX(SHA256(_raw_json)) AS _row_hash, _source_snapshot_at
FROM normalized
`);

publish(name('transactions_classified'),{...config,type:'table'}).query(ctx=>`
WITH counted AS (
  SELECT t.*,1 AS _source_count,
    COUNT(*) OVER(PARTITION BY transaction_id) AS _id_versions
  FROM ${ref(ctx,'transactions_typed')} t
), classified AS (
  SELECT t.* EXCEPT(_errors),ARRAY_CONCAT(t._errors,
    IF(t.transaction_id IS NOT NULL AND t._id_versions>1,['transaction_id.not_unique'],ARRAY<STRING>[]),
    IF(t.customer_id IS NOT NULL AND c.customer_id IS NULL,['customer_id.foreign_key'],ARRAY<STRING>[]),
    IF(t.product_id IS NOT NULL AND p.product_id IS NULL,
      IF(q.product_id IS NOT NULL,['product_id.quarantined_parent'],['product_id.foreign_key']),ARRAY<STRING>[]),
    IF(t.customer_id IS NOT NULL AND p.product_id IS NOT NULL AND t.customer_id!=p.customer_id,
      ['customer_id.product_owner_mismatch'],ARRAY<STRING>[])
  ) AS _errors
  FROM counted t
  LEFT JOIN \`${P}.bank_stage.transactions_customers_${run}\` c ON c.customer_id=t.customer_id
  LEFT JOIN \`${P}.bank_stage.transactions_products_${run}\` p ON p.product_id=t.product_id
  LEFT JOIN \`${P}.bank_stage.transactions_parent_quarantine_${run}\` q ON q.product_id=t.product_id
)
SELECT *,IF(ARRAY_LENGTH(_errors)=0,'ACCEPTED','REJECTED') AS _disposition FROM classified
`);

publish(name('transactions_candidate'),{...config,type:'table'}).query(ctx=>`
SELECT ${columns}, '${run}' AS _curation_run_id,
  '${C.version}' AS _contract_version, _source_snapshot_at
FROM ${ref(ctx,'transactions_classified')} WHERE _disposition='ACCEPTED'
`);

publish(name('transactions_checks'),{...config,type:'table'}).query(ctx=>`
WITH counts AS (
  SELECT COALESCE(SUM(_source_count),0) AS input_rows,
    COUNTIF(_disposition='ACCEPTED') AS accepted,
    COALESCE(SUM(IF(_disposition='REJECTED',_source_count,0)),0) AS rejected,
    COALESCE(SUM(IF(_disposition='ACCEPTED',_source_count-1,0)),0) AS duplicates
  FROM ${ref(ctx,'transactions_classified')}
), metrics AS (
  SELECT 'nonempty_input' AS rule_id, input_rows AS observed, 1 AS expected, input_rows>0 AS passed, 'BLOCK' AS severity FROM counts
  UNION ALL SELECT 'rejected_rows',rejected,0,rejected=0,'WARN' FROM counts
  UNION ALL SELECT 'nonempty_candidate',accepted,1,accepted>0,'BLOCK' FROM counts
  UNION ALL SELECT 'unapproved_rejections',COUNTIF(EXISTS(SELECT 1 FROM UNNEST(_errors) e WHERE e NOT IN (${H.list(C.partialPublicationAllowedErrors)}))),0,
    COUNTIF(EXISTS(SELECT 1 FROM UNNEST(_errors) e WHERE e NOT IN (${H.list(C.partialPublicationAllowedErrors)})))=0,'BLOCK'
    FROM ${ref(ctx,'transactions_classified')}
  UNION ALL SELECT 'reconciliation',input_rows,accepted+rejected+duplicates,input_rows=accepted+rejected+duplicates,'BLOCK' FROM counts
  UNION ALL SELECT 'source_reconciliation',input_rows,(SELECT COUNT(*) FROM ${ref(ctx,'transactions_input')}),input_rows=(SELECT COUNT(*) FROM ${ref(ctx,'transactions_input')}),'BLOCK' FROM counts
  UNION ALL SELECT 'candidate_count',(SELECT COUNT(*) FROM ${ref(ctx,'transactions_candidate')}),accepted,(SELECT COUNT(*) FROM ${ref(ctx,'transactions_candidate')})=accepted,'BLOCK' FROM counts
  UNION ALL SELECT 'candidate_pk_duplicates',COUNT(*)-COUNT(DISTINCT transaction_id),0,COUNT(*)=COUNT(DISTINCT transaction_id),'BLOCK' FROM ${ref(ctx,'transactions_candidate')}
  UNION ALL SELECT 'process_date_before_transaction_date',COUNTIF(process_date<DATE(transaction_date)),0,COUNTIF(process_date<DATE(transaction_date))=0,'WARN' FROM ${ref(ctx,'transactions_typed')}
  UNION ALL SELECT 'incomplete_coordinate_pair',COUNTIF((latitude IS NULL)!=(longitude IS NULL)),0,COUNTIF((latitude IS NULL)!=(longitude IS NULL))=0,'WARN' FROM ${ref(ctx,'transactions_typed')}
  UNION ALL SELECT 'negative_amount',COUNTIF(amount<0),0,COUNTIF(amount<0)=0,'WARN' FROM ${ref(ctx,'transactions_typed')}
  UNION ALL SELECT 'currency_differs_from_product',COUNTIF(t.currency!=p.currency),0,COUNTIF(t.currency!=p.currency)=0,'WARN'
    FROM ${ref(ctx,'transactions_typed')} t JOIN \`${P}.bank_stage.transactions_products_${run}\` p ON t.product_id=p.product_id

)
SELECT * FROM metrics
`);

operate(name('transactions_record_quality')).config({schema:'bank_ops',tags:['transactions']}).queries(ctx=>`
CREATE TABLE IF NOT EXISTS ${rejected} (
  run_id STRING, recorded_at TIMESTAMP, row_hash STRING, raw_json STRING,
  source_count INT64, errors ARRAY<STRING>
) PARTITION BY DATE(recorded_at) OPTIONS(partition_expiration_days=30);
INSERT INTO ${rejected}
SELECT '${run}',CURRENT_TIMESTAMP(),_row_hash,_raw_json,_source_count,_errors
FROM ${ref(ctx,'transactions_classified')} WHERE _disposition='REJECTED';
INSERT INTO ${audit}
SELECT '${run}',CURRENT_TIMESTAMP(),rule_id,observed,expected,passed,severity
FROM ${ref(ctx,'transactions_checks')};
UPDATE ${runs} SET
  status=IF(EXISTS(SELECT 1 FROM ${ref(ctx,'transactions_checks')} WHERE severity='BLOCK' AND NOT passed),'BLOCKED','VALIDATED'),
  finished_at=IF(EXISTS(SELECT 1 FROM ${ref(ctx,'transactions_checks')} WHERE severity='BLOCK' AND NOT passed),CURRENT_TIMESTAMP(),NULL)
WHERE run_id='${run}' AND table_name='transactions';
`);

assert(name('transactions_publish_gate')).config({
  tags:['transactions'], dependencies:[name('transactions_record_quality')]
}).query(ctx=>`SELECT rule_id FROM ${ref(ctx,'transactions_checks')} WHERE severity='BLOCK' AND NOT passed
UNION ALL SELECT 'quarantine_reconciliation'
FROM (SELECT 1 AS singleton)
WHERE (SELECT COALESCE(SUM(source_count),0) FROM ${rejected} WHERE run_id='${run}')
  != (SELECT observed FROM ${ref(ctx,'transactions_checks')} WHERE rule_id='rejected_rows')`);

operate('transactions').config({
  schema:'bank_curated',hasOutput:true,tags:['transactions'],
  dependencies:[name('transactions_publish_gate')]
}).queries(ctx=>`
DECLARE transaction_open BOOL DEFAULT FALSE;
BEGIN
  CREATE TABLE IF NOT EXISTS ${ctx.self()}
  PARTITION BY process_date CLUSTER BY product_id,customer_id AS
  SELECT * FROM ${ref(ctx,'transactions_candidate')} WHERE FALSE;
  BEGIN TRANSACTION;
  SET transaction_open=TRUE;
  DELETE FROM ${ctx.self()} WHERE TRUE;
  INSERT INTO ${ctx.self()} (${columns},_curation_run_id,_contract_version,_source_snapshot_at)
  SELECT ${columns},_curation_run_id,_contract_version,_source_snapshot_at
  FROM ${ref(ctx,'transactions_candidate')};
  UPDATE ${runs} SET status=IF(EXISTS(SELECT 1 FROM ${ref(ctx,'transactions_checks')} WHERE rule_id='rejected_rows' AND observed>0),'SUCCEEDED_WITH_REJECTIONS','SUCCEEDED'),finished_at=CURRENT_TIMESTAMP(),
    published_rows=(SELECT COUNT(*) FROM ${ctx.self()}) WHERE run_id='${run}' AND table_name='transactions';
  COMMIT TRANSACTION;
  SET transaction_open=FALSE;
EXCEPTION WHEN ERROR THEN
  IF transaction_open THEN ROLLBACK TRANSACTION; END IF;
  UPDATE ${runs} SET status='FAILED',finished_at=CURRENT_TIMESTAMP() WHERE run_id='${run}' AND table_name='transactions';
  RAISE;
END;
`);
