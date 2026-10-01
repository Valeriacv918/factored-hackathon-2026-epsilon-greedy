const lit=s=>JSON.stringify(String(s));
const list=values=>values.map(lit).join(',');
const ident=n=>'`'+n+'`';
function normalized(f) {
 const value=`NULLIF(TRIM(${ident(f.name)}), '')`;
 return ['source_currency','target_currency'].includes(f.name) ? `UPPER(${value})` : value;
}
function typed(f) { return f.type==='STRING' ? ident(f.name) : `SAFE_CAST(${ident(f.name)} AS ${f.type})`; }
function errors(C) {
 const expr=[];
 const rule=(condition,id)=>expr.push(`IF(${condition},${lit(id)},NULL)`);
 for(const f of C.fields) {
  const n=ident(f.name);
  if(f.required) rule(`${n} IS NULL`,`${f.name}.required`);
  if(f.maxLength) rule(`CHAR_LENGTH(${n})>${f.maxLength}`,`${f.name}.max_length`);
  if(f.type!=='STRING') rule(`${n} IS NOT NULL AND (${typed(f)}) IS NULL`,`${f.name}.conversion`);
 }
 for(const n of ['source_currency','target_currency']) rule(`${n} IS NOT NULL AND NOT REGEXP_CONTAINS(${n},r'^[A-Z]{3}$')`,`${n}.format`);
 for(const n of ['exchange_rate','buy_rate','sell_rate']) {
  const v=`SAFE_CAST(${n} AS BIGNUMERIC)`;
  rule(`${v}!=TRUNC(${v},6)`,`${n}.scale`);
  rule(`ABS(${v})>=1000000`,`${n}.precision`);
  rule(`${v}<=0`,`${n}.positive`);
 }
 return `ARRAY(SELECT code FROM UNNEST([${expr.join(',\n')}]) code WHERE code IS NOT NULL)`;
}
module.exports={lit,list,ident,normalized,typed,errors};
