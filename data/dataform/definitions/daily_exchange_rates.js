const C = require('includes/daily_exchange_rates_contract');
const H = require('includes/daily_exchange_rates_helpers');
const P = dataform.projectConfig.defaultDatabase;
const run = dataform.projectConfig.vars.run_id;
if(!/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(run || '')) throw Error('run_id must be a letter followed by <=63 letters, digits or underscores');
const name = base => `${base}_${run}`;
const config = {schema:'bank_stage', tags:['daily_exchange_rates'], bigquery:{additionalOptions:{expiration_timestamp:'TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)'}}};
const ref = (ctx, base) => ctx.ref('bank_stage',name(base));
const runs = '`'+P+'.bank_ops.curation_runs`';
const audit = '`'+P+'.bank_ops.curation_results`';
const rejected = '`'+P+'.bank_quarantine.daily_exchange_rates_rejected`';
const columns = C.fields.map(f=>H.ident(f.name)).join(', ');

declare({database:P,schema:'bank_raw',name:'daily_exchange_rates'});

operate(name('daily_exchange_rates_input')).config({schema:'bank_stage',hasOutput:true,tags:['daily_exchange_rates']}).queries(ctx=>`
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
ASSERT NOT EXISTS(SELECT 1 FROM ${runs} WHERE run_id='${run}' AND table_name='daily_exchange_rates') AS 'run_id already exists; use a fresh ID';
INSERT INTO ${runs} VALUES('${run}','daily_exchange_rates','${C.version}',${H.lit(JSON.stringify(C))},snapshot_at,
  CURRENT_TIMESTAMP(),NULL,'RUNNING',NULL,NULL,[${H.list(C.pendingRules)}]);
BEGIN
  CREATE TABLE ${ctx.self()}
  OPTIONS(expiration_timestamp=TIMESTAMP_ADD(CURRENT_TIMESTAMP(),INTERVAL 7 DAY)) AS
  SELECT r.*, snapshot_at AS _source_snapshot_at
  FROM ${ctx.ref('bank_raw','daily_exchange_rates')} AS r FOR SYSTEM_TIME AS OF snapshot_at;
  UPDATE ${runs} SET input_rows=(SELECT COUNT(*) FROM ${ctx.self()}) WHERE run_id='${run}' AND table_name='daily_exchange_rates';
EXCEPTION WHEN ERROR THEN
  UPDATE ${runs} SET status='FAILED',finished_at=CURRENT_TIMESTAMP() WHERE run_id='${run}' AND table_name='daily_exchange_rates';
  RAISE;
END;
`);

publish(name('daily_exchange_rates_typed'),{...config,type:'table'}).query(ctx=>`
WITH normalized AS (
  SELECT ${C.fields.map(f=>`${H.normalized(f,C)} AS ${H.ident(f.name)}`).join(',\n')},
    TO_JSON_STRING(STRUCT(${C.fields.map(f=>`r.${H.ident(f.name)}`).join(',')})) AS _raw_json,
    _source_snapshot_at
  FROM ${ref(ctx,'daily_exchange_rates_input')} r
)
SELECT ${C.fields.map(f=>`${H.typed(f,C)} AS ${H.ident(f.name)}`).join(',\n')},
  ${H.errors(C)} AS _errors,
  _raw_json, TO_HEX(SHA256(_raw_json)) AS _row_hash, _source_snapshot_at
FROM normalized
`);

publish(name('daily_exchange_rates_classified'),{...config,type:'table'}).query(ctx=>`
WITH counted AS (
 SELECT t.*,1 AS _source_count,
  COUNT(*) OVER(PARTITION BY \`date\`,source_currency,target_currency) AS _key_versions
 FROM ${ref(ctx,'daily_exchange_rates_typed')} t
), classified AS (
 SELECT * EXCEPT(_errors),ARRAY_CONCAT(_errors,
  IF(\`date\` IS NOT NULL AND source_currency IS NOT NULL AND target_currency IS NOT NULL
   AND _key_versions>1,['composite_key.not_unique'],ARRAY<STRING>[])
 ) AS _errors FROM counted
)
SELECT *,IF(ARRAY_LENGTH(_errors)=0,'ACCEPTED','REJECTED') AS _disposition FROM classified
`);

publish(name('daily_exchange_rates_candidate'),{...config,type:'table'}).query(ctx=>`
SELECT ${columns}, '${run}' AS _curation_run_id,
  '${C.version}' AS _contract_version, _source_snapshot_at
FROM ${ref(ctx,'daily_exchange_rates_classified')} WHERE _disposition='ACCEPTED'
`);

publish(name('daily_exchange_rates_checks'),{...config,type:'table'}).query(ctx=>`
WITH counts AS (
  SELECT COALESCE(SUM(_source_count),0) AS input_rows,
    COUNTIF(_disposition='ACCEPTED') AS accepted,
    COALESCE(SUM(IF(_disposition='REJECTED',_source_count,0)),0) AS rejected,
    COALESCE(SUM(IF(_disposition='ACCEPTED',_source_count-1,0)),0) AS duplicates
  FROM ${ref(ctx,'daily_exchange_rates_classified')}
), metrics AS (
  SELECT 'nonempty_input' AS rule_id, input_rows AS observed, 1 AS expected, input_rows>0 AS passed, 'BLOCK' AS severity FROM counts
  UNION ALL SELECT 'rejected_rows',rejected,${C.maxRejectedRows},rejected<=${C.maxRejectedRows},'BLOCK' FROM counts
  UNION ALL SELECT 'reconciliation',input_rows,accepted+rejected+duplicates,input_rows=accepted+rejected+duplicates,'BLOCK' FROM counts
  UNION ALL SELECT 'source_reconciliation',input_rows,(SELECT COUNT(*) FROM ${ref(ctx,'daily_exchange_rates_input')}),input_rows=(SELECT COUNT(*) FROM ${ref(ctx,'daily_exchange_rates_input')}),'BLOCK' FROM counts
  UNION ALL SELECT 'candidate_count',(SELECT COUNT(*) FROM ${ref(ctx,'daily_exchange_rates_candidate')}),accepted,(SELECT COUNT(*) FROM ${ref(ctx,'daily_exchange_rates_candidate')})=accepted,'BLOCK' FROM counts
  UNION ALL SELECT 'candidate_composite_key_duplicate_groups',COUNT(*),0,COUNT(*)=0,'BLOCK'
  FROM (SELECT \`date\`,source_currency,target_currency
    FROM ${ref(ctx,'daily_exchange_rates_candidate')}
    GROUP BY \`date\`,source_currency,target_currency HAVING COUNT(*)>1)
  UNION ALL SELECT 'buy_above_sell',COUNTIF(buy_rate>sell_rate),0,COUNTIF(buy_rate>sell_rate)=0,'WARN' FROM ${ref(ctx,'daily_exchange_rates_typed')}
  UNION ALL SELECT 'rate_outside_buy_sell',COUNTIF(exchange_rate<buy_rate OR exchange_rate>sell_rate),0,COUNTIF(exchange_rate<buy_rate OR exchange_rate>sell_rate)=0,'WARN' FROM ${ref(ctx,'daily_exchange_rates_typed')}
  UNION ALL SELECT 'same_currency_not_one',COUNTIF(source_currency=target_currency AND exchange_rate!=1),0,COUNTIF(source_currency=target_currency AND exchange_rate!=1)=0,'WARN' FROM ${ref(ctx,'daily_exchange_rates_typed')}
  UNION ALL SELECT 'missing_calendar_dates_within_pair_span',COALESCE(SUM(gaps),0),0,COALESCE(SUM(gaps),0)=0,'WARN'
  FROM (SELECT DATE_DIFF(MAX(\`date\`),MIN(\`date\`),DAY)+1-COUNT(DISTINCT \`date\`) AS gaps
    FROM ${ref(ctx,'daily_exchange_rates_candidate')} GROUP BY source_currency,target_currency)

)
SELECT * FROM metrics
`);

operate(name('daily_exchange_rates_record_quality')).config({schema:'bank_ops',tags:['daily_exchange_rates']}).queries(ctx=>`
CREATE TABLE IF NOT EXISTS ${rejected} (
  run_id STRING, recorded_at TIMESTAMP, row_hash STRING, raw_json STRING,
  source_count INT64, errors ARRAY<STRING>
) PARTITION BY DATE(recorded_at) OPTIONS(partition_expiration_days=30);
INSERT INTO ${rejected}
SELECT '${run}',CURRENT_TIMESTAMP(),_row_hash,_raw_json,_source_count,_errors
FROM ${ref(ctx,'daily_exchange_rates_classified')} WHERE _disposition='REJECTED';
INSERT INTO ${audit}
SELECT '${run}',CURRENT_TIMESTAMP(),rule_id,observed,expected,passed,severity
FROM ${ref(ctx,'daily_exchange_rates_checks')};
UPDATE ${runs} SET
  status=IF(EXISTS(SELECT 1 FROM ${ref(ctx,'daily_exchange_rates_checks')} WHERE severity='BLOCK' AND NOT passed),'BLOCKED','VALIDATED'),
  finished_at=IF(EXISTS(SELECT 1 FROM ${ref(ctx,'daily_exchange_rates_checks')} WHERE severity='BLOCK' AND NOT passed),CURRENT_TIMESTAMP(),NULL)
WHERE run_id='${run}' AND table_name='daily_exchange_rates';
`);

assert(name('daily_exchange_rates_publish_gate')).config({
  tags:['daily_exchange_rates'], dependencies:[name('daily_exchange_rates_record_quality')]
}).query(ctx=>`SELECT * FROM ${ref(ctx,'daily_exchange_rates_checks')} WHERE severity='BLOCK' AND NOT passed`);

operate('daily_exchange_rates').config({
  schema:'bank_curated',hasOutput:true,tags:['daily_exchange_rates'],
  dependencies:[name('daily_exchange_rates_publish_gate')]
}).queries(ctx=>`
DECLARE transaction_open BOOL DEFAULT FALSE;
BEGIN
  CREATE TABLE IF NOT EXISTS ${ctx.self()} CLUSTER BY source_currency,target_currency AS
  SELECT * FROM ${ref(ctx,'daily_exchange_rates_candidate')} WHERE FALSE;
  BEGIN TRANSACTION;
  SET transaction_open=TRUE;
  DELETE FROM ${ctx.self()} WHERE TRUE;
  INSERT INTO ${ctx.self()} (${columns},_curation_run_id,_contract_version,_source_snapshot_at)
  SELECT ${columns},_curation_run_id,_contract_version,_source_snapshot_at
  FROM ${ref(ctx,'daily_exchange_rates_candidate')};
  UPDATE ${runs} SET status='SUCCEEDED',finished_at=CURRENT_TIMESTAMP(),
    published_rows=(SELECT COUNT(*) FROM ${ctx.self()}) WHERE run_id='${run}' AND table_name='daily_exchange_rates';
  COMMIT TRANSACTION;
  SET transaction_open=FALSE;
EXCEPTION WHEN ERROR THEN
  IF transaction_open THEN ROLLBACK TRANSACTION; END IF;
  UPDATE ${runs} SET status='FAILED',finished_at=CURRENT_TIMESTAMP() WHERE run_id='${run}' AND table_name='daily_exchange_rates';
  RAISE;
END;
`);
