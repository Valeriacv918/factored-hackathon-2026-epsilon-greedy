// GoogleSQL accepts JSON-compatible double-quoted string literals.
const lit = s => JSON.stringify(String(s));
const list = values => values.map(lit).join(',');
const clean = name => `NULLIF(TRIM(${name}), '')`;

function normalized(field, contract) {
  if(['description','resolution'].includes(field.name)) return `IF(NULLIF(TRIM(${field.name}), '') IS NULL,NULL,${field.name})`;
  const value=clean(field.name), mapping=contract.mappings[field.name];
  return mapping ? `CASE ${value} ${Object.entries(mapping).map(([a,b]) => `WHEN ${lit(a)} THEN ${lit(b)}`).join(' ')} ELSE ${value} END` : value;
}
function typed(field, contract) {
  const n=field.name;
  if(field.type==='STRING') return n;
  if(field.type==='BOOL') return `CASE WHEN LOWER(${n}) IN (${list(contract.booleanTrue)}) THEN TRUE WHEN LOWER(${n}) IN (${list(contract.booleanFalse)}) THEN FALSE END`;
  if(field.type==='INT64') return `SAFE_CAST(SAFE_CAST(${n} AS BIGNUMERIC) AS INT64)`;
  return `SAFE_CAST(${n} AS ${field.type})`;
}
function errors(contract) {
  const expressions=[];
  const rule=(condition,id)=>expressions.push(`IF(${condition}, ${lit(id)}, NULL)`);
  for(const f of contract.fields) {
    const n=f.name;
    if(f.required) rule(`${n} IS NULL`,`${n}.required`);
    if(f.maxLength) rule(`CHAR_LENGTH(${n}) > ${f.maxLength}`,`${n}.max_length`);
    if(contract.domains[n]) rule(`${n} IS NOT NULL AND ${n} NOT IN (${list(contract.domains[n])})`,`${n}.domain`);
    if(f.type!=='STRING') rule(`${n} IS NOT NULL AND (${typed(f,contract)}) IS NULL`,`${n}.conversion`);
  }
  for(const n of ['claimed_amount','compensation_granted']) {
    const v=`SAFE_CAST(${n} AS BIGNUMERIC)`;
    rule(`${v}!=TRUNC(${v},2)`,`${n}.scale`);
    rule(`ABS(${v})>=10000000000000`,`${n}.precision`);
  }
  for(const n of ['resolution_days','resolution_satisfaction']) {
    const v=`SAFE_CAST(${n} AS BIGNUMERIC)`;
    rule(`${v}!=TRUNC(${v})`,`${n}.integer`);
  }
  rule('SAFE_CAST(resolution_satisfaction AS BIGNUMERIC)<1 OR SAFE_CAST(resolution_satisfaction AS BIGNUMERIC)>5','resolution_satisfaction.range');
  return `ARRAY(SELECT code FROM UNNEST([${expressions.join(',\n')}]) code WHERE code IS NOT NULL)`;
}
module.exports={lit,list,clean,normalized,typed,errors};

function warnings() { return `ARRAY(SELECT code FROM UNNEST([IF(t.customer_id IS NOT NULL AND p.product_id IS NOT NULL AND t.customer_id!=p.customer_id,'customer_id.product_owner_mismatch',NULL),
IF(t.process_date<DATE(t.creation_date),'process_date.before_creation_date',NULL),
IF((t.claimed_amount IS NOT NULL OR t.compensation_granted IS NOT NULL) AND t.currency IS NULL,'currency.missing_with_amount',NULL),
IF(t.currency IS NOT NULL AND p.currency IS NOT NULL AND t.currency!=p.currency,'currency.differs_from_product',NULL),
IF(t.resolution_days<0,'resolution_days.negative',NULL),
IF(t.claimed_amount<0,'claimed_amount.negative',NULL),
IF(t.compensation_granted<0,'compensation_granted.negative',NULL),
IF(t.closing_date<t.resolution_date,'closing_date.before_resolution',NULL),
IF(t.resolution_days!=DATE_DIFF(DATE(t.resolution_date),DATE(t.creation_date),DAY),'resolution_days.calendar_difference',NULL),
IF(t.assignment_date<t.creation_date,'assignment_date.before_creation',NULL),
IF(t.first_response_date<t.creation_date,'first_response_date.before_creation',NULL),
IF(t.resolution_date<t.creation_date,'resolution_date.before_creation',NULL),
IF(t.closing_date<t.creation_date,'closing_date.before_creation',NULL)]) code WHERE code IS NOT NULL)`; }
module.exports.warnings=warnings;
