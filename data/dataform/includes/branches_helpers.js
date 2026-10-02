// GoogleSQL accepts JSON-compatible double-quoted string literals.
const lit = s => JSON.stringify(String(s));
const list = values => values.map(lit).join(',');
const clean = name => `NULLIF(TRIM(${name}), '')`;

function normalized(field, contract) {
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
  for(const n of ['atm_count','teller_window_count']) {
    const v=`SAFE_CAST(${n} AS BIGNUMERIC)`;
    rule(`${v}!=TRUNC(${v})`,`${n}.integer`);
    rule(`${v}<0`,`${n}.nonnegative`);
  }
  for(const [n,limit] of [['latitude',90],['longitude',180]]) {
    const v=`SAFE_CAST(${n} AS BIGNUMERIC)`;
    rule(`${v}!=TRUNC(${v},7)`,`${n}.scale`);
    rule(`ABS(${v})>=1000`,`${n}.precision`);
    rule(`ABS(${v})>${limit}`,`${n}.range`);
  }
  return `ARRAY(SELECT code FROM UNNEST([${expressions.join(',\n')}]) code WHERE code IS NOT NULL)`;
}
module.exports={lit,list,clean,normalized,typed,errors};
