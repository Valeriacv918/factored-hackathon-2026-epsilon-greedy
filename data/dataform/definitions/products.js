const C = require('includes/products_contract');
const H = require('includes/products_helpers');
const P = dataform.projectConfig.defaultDatabase;
const run = dataform.projectConfig.vars.run_id;
if(!/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(run || '')) throw Error('run_id must be a letter followed by <=63 letters, digits or underscores');
const name = base => `${base}_${run}`;
const config = {schema:'bank_stage', tags:['products'], bigquery:{additionalOptions:{expiration_timestamp:'TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)'}}};
const ref = (ctx, base) => ctx.ref('bank_stage',name(base));
const runs = '`'+P+'.bank_ops.curation_runs`';
const audit = '`'+P+'.bank_ops.curation_results`';
const rejected = '`'+P+'.bank_quarantine.products_rejected`';
const columns = C.fields.map(f=>f.name).join(', ');

declare({database:P,schema:'bank_raw',name:'products'});

operate(name('products_input')).config({schema:'bank_stage',hasOutput:true,tags:['products']}).queries(ctx=>`
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
ASSERT NOT EXISTS(SELECT 1 FROM ${runs} WHERE run_id='${run}' AND table_name='products') AS 'run_id already exists; use a fresh ID';
INSERT INTO ${runs} VALUES('${run}','products','${C.version}',${H.lit(JSON.stringify(C))},snapshot_at,
  CURRENT_TIMESTAMP(),NULL,'RUNNING',NULL,NULL,[${H.list(C.pendingRules)}]);
BEGIN
  CREATE TABLE ${ctx.self()}
  OPTIONS(expiration_timestamp=TIMESTAMP_ADD(CURRENT_TIMESTAMP(),INTERVAL 7 DAY)) AS
  SELECT r.*, snapshot_at AS _source_snapshot_at
  FROM ${ctx.ref('bank_raw','products')} AS r FOR SYSTEM_TIME AS OF snapshot_at;
  CREATE TABLE \`${P}.bank_stage.products_customers_${run}\`
  OPTIONS(expiration_timestamp=TIMESTAMP_ADD(CURRENT_TIMESTAMP(),INTERVAL 7 DAY)) AS
  SELECT customer_id, _curation_run_id FROM \`${P}.bank_curated.customers\`
  FOR SYSTEM_TIME AS OF snapshot_at;
  ASSERT (SELECT COUNT(*) FROM \`${P}.bank_stage.products_customers_${run}\`)>0
    AS 'Published customers reference is empty';
  UPDATE ${runs} SET input_rows=(SELECT COUNT(*) FROM ${ctx.self()}) WHERE run_id='${run}' AND table_name='products';
EXCEPTION WHEN ERROR THEN
  UPDATE ${runs} SET status='FAILED',finished_at=CURRENT_TIMESTAMP() WHERE run_id='${run}' AND table_name='products';
  RAISE;
END;
`);

publish(name('products_typed'),{...config,type:'table'}).query(ctx=>`
WITH normalized AS (
  SELECT ${C.fields.map(f=>`${H.normalized(f,C)} AS ${f.name}`).join(',\n')},
    TO_JSON_STRING(STRUCT(${C.fields.map(f=>`r.${f.name}`).join(',')})) AS _raw_json,
    _source_snapshot_at
  FROM ${ref(ctx,'products_input')} r
)
SELECT ${C.fields.map(f=>`${H.typed(f,C)} AS ${f.name}`).join(',\n')},
  ${H.errors(C)} AS _errors,
  _raw_json, TO_HEX(SHA256(_raw_json)) AS _row_hash, _source_snapshot_at
FROM normalized
`);

publish(name('products_classified'),{...config,type:'table'}).query(ctx=>`
WITH counted AS (
  SELECT t.*, 1 AS _source_count,
    COUNT(*) OVER(PARTITION BY product_id) AS _id_versions,
    COUNT(*) OVER(PARTITION BY product_number) AS _number_versions
  FROM ${ref(ctx,'products_typed')} t
), classified AS (
  SELECT * EXCEPT(_errors), ARRAY_CONCAT(_errors,
    IF(product_id IS NOT NULL AND _id_versions>1,['product_id.not_unique'],ARRAY<STRING>[]),
    IF(product_number IS NOT NULL AND _number_versions>1,['duplicate_product_number'],ARRAY<STRING>[]),
    IF(customer_id IS NOT NULL AND NOT EXISTS(
      SELECT 1 FROM \`${P}.bank_stage.products_customers_${run}\` c
      WHERE c.customer_id=counted.customer_id),['customer_id.foreign_key'],ARRAY<STRING>[])
  ) AS _errors FROM counted
)
SELECT *, IF(ARRAY_LENGTH(_errors)=0,'ACCEPTED','REJECTED') AS _disposition
FROM classified
`);

publish(name('products_candidate'),{...config,type:'table'}).query(ctx=>`
SELECT ${columns}, '${run}' AS _curation_run_id,
  '${C.version}' AS _contract_version, _source_snapshot_at
FROM ${ref(ctx,'products_classified')} WHERE _disposition='ACCEPTED'
`);

publish(name('products_checks'),{...config,type:'table'}).query(ctx=>`
WITH counts AS (
  SELECT COALESCE(SUM(_source_count),0) AS input_rows,
    COUNTIF(_disposition='ACCEPTED') AS accepted,
    COALESCE(SUM(IF(_disposition='REJECTED',_source_count,0)),0) AS rejected,
    COALESCE(SUM(IF(_disposition='ACCEPTED',_source_count-1,0)),0) AS duplicates
  FROM ${ref(ctx,'products_classified')}
), metrics AS (
  SELECT 'nonempty_input' AS rule_id, input_rows AS observed, 1 AS expected, input_rows>0 AS passed, 'BLOCK' AS severity FROM counts
  UNION ALL SELECT 'rejected_rows',rejected,0,rejected=0,'WARN' FROM counts
  UNION ALL SELECT 'nonempty_candidate',accepted,1,accepted>0,'BLOCK' FROM counts
  UNION ALL SELECT 'unapproved_rejections',COUNTIF(EXISTS(SELECT 1 FROM UNNEST(_errors) e WHERE e NOT IN (${H.list(C.partialPublicationAllowedErrors)}))),0,
    COUNTIF(EXISTS(SELECT 1 FROM UNNEST(_errors) e WHERE e NOT IN (${H.list(C.partialPublicationAllowedErrors)})))=0,'BLOCK'
    FROM ${ref(ctx,'products_classified')}
  UNION ALL SELECT 'reconciliation',input_rows,accepted+rejected+duplicates,input_rows=accepted+rejected+duplicates,'BLOCK' FROM counts
  UNION ALL SELECT 'source_reconciliation',input_rows,(SELECT COUNT(*) FROM ${ref(ctx,'products_input')}),input_rows=(SELECT COUNT(*) FROM ${ref(ctx,'products_input')}),'BLOCK' FROM counts
  UNION ALL SELECT 'candidate_count',(SELECT COUNT(*) FROM ${ref(ctx,'products_candidate')}),accepted,(SELECT COUNT(*) FROM ${ref(ctx,'products_candidate')})=accepted,'BLOCK' FROM counts
  UNION ALL SELECT 'candidate_pk_duplicates',COUNT(*)-COUNT(DISTINCT product_id),0,COUNT(*)=COUNT(DISTINCT product_id),'BLOCK' FROM ${ref(ctx,'products_candidate')}
  UNION ALL SELECT 'candidate_number_duplicates',COUNT(*)-COUNT(DISTINCT product_number),0,COUNT(*)=COUNT(DISTINCT product_number),'BLOCK' FROM ${ref(ctx,'products_candidate')}
  UNION ALL SELECT 'exact_copies_discarded',duplicates,CAST(NULL AS INT64),TRUE,'INFO' FROM counts
  UNION ALL SELECT 'last_updated_before_opening',COUNTIF(DATE(last_updated)<opening_date),0,COUNTIF(DATE(last_updated)<opening_date)=0,'WARN' FROM ${ref(ctx,'products_candidate')}
  UNION ALL SELECT 'reference_customer_runs',COUNT(DISTINCT _curation_run_id),1,COUNT(DISTINCT _curation_run_id)=1,'BLOCK' FROM \`${P}.bank_stage.products_customers_${run}\`

)
SELECT * FROM metrics
`);

operate(name('products_record_quality')).config({schema:'bank_ops',tags:['products']}).queries(ctx=>`
CREATE TABLE IF NOT EXISTS ${rejected} (
  run_id STRING, recorded_at TIMESTAMP, row_hash STRING, raw_json STRING,
  source_count INT64, errors ARRAY<STRING>
) PARTITION BY DATE(recorded_at) OPTIONS(partition_expiration_days=30);
INSERT INTO ${rejected}
SELECT '${run}',CURRENT_TIMESTAMP(),_row_hash,_raw_json,_source_count,_errors
FROM ${ref(ctx,'products_classified')} WHERE _disposition='REJECTED';
INSERT INTO ${audit}
SELECT '${run}',CURRENT_TIMESTAMP(),rule_id,observed,expected,passed,severity
FROM ${ref(ctx,'products_checks')};
UPDATE ${runs} SET
  status=IF(EXISTS(SELECT 1 FROM ${ref(ctx,'products_checks')} WHERE severity='BLOCK' AND NOT passed),'BLOCKED','VALIDATED'),
  finished_at=IF(EXISTS(SELECT 1 FROM ${ref(ctx,'products_checks')} WHERE severity='BLOCK' AND NOT passed),CURRENT_TIMESTAMP(),NULL)
WHERE run_id='${run}' AND table_name='products';
`);

assert(name('products_publish_gate')).config({
  tags:['products'], dependencies:[name('products_record_quality')]
}).query(ctx=>`SELECT * FROM ${ref(ctx,'products_checks')} WHERE severity='BLOCK' AND NOT passed`);

operate('products').config({
  schema:'bank_curated',hasOutput:true,tags:['products'],
  dependencies:[name('products_publish_gate')]
}).queries(ctx=>`
DECLARE transaction_open BOOL DEFAULT FALSE;
BEGIN
  CREATE TABLE IF NOT EXISTS ${ctx.self()} AS
  SELECT * FROM ${ref(ctx,'products_candidate')} WHERE FALSE;
  BEGIN TRANSACTION;
  SET transaction_open=TRUE;
  DELETE FROM ${ctx.self()} WHERE TRUE;
  INSERT INTO ${ctx.self()} (${columns},_curation_run_id,_contract_version,_source_snapshot_at)
  SELECT ${columns},_curation_run_id,_contract_version,_source_snapshot_at
  FROM ${ref(ctx,'products_candidate')};
  UPDATE ${runs} SET status=IF(EXISTS(SELECT 1 FROM ${ref(ctx,'products_checks')} WHERE rule_id='rejected_rows' AND observed>0),'SUCCEEDED_WITH_REJECTIONS','SUCCEEDED'),finished_at=CURRENT_TIMESTAMP(),
    published_rows=(SELECT COUNT(*) FROM ${ctx.self()}) WHERE run_id='${run}' AND table_name='products';
  COMMIT TRANSACTION;
  SET transaction_open=FALSE;
EXCEPTION WHEN ERROR THEN
  IF transaction_open THEN ROLLBACK TRANSACTION; END IF;
  UPDATE ${runs} SET status='FAILED',finished_at=CURRENT_TIMESTAMP() WHERE run_id='${run}' AND table_name='products';
  RAISE;
END;
`);
