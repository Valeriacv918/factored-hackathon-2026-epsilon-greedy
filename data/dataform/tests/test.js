// Local graph tests; these do not replace compilation by the Dataform service.
const fs=require('fs');
const vm=require('vm');
const path=require('path');
const nodeAssert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const C=require('../includes/customers_contract');
const H=require('../includes/sql_helpers');
const source=fs.readFileSync(path.join(root,'definitions/customers.js'),'utf8');

function build(run) {
  const actions=[];
  function register(type,name,config={}) {
    const a={type,name,config,refs:[]}; actions.push(a);
    const ctx={self:()=>`\`project.${config.schema || 'bank_ops'}.${name}\``,
      ref:(schema,n)=>{a.refs.push(n || schema);return `\`project.${n ? schema : 'bank_stage'}.${n || schema}\``;}};
    const chain={config:cfg=>{Object.assign(config,cfg);return chain;},
      query:fn=>{a.sql=fn(ctx);return a;},queries:fn=>{a.sql=fn(ctx);return a;}};
    return chain;
  }
  vm.runInNewContext(source,{
    require:name=>require(path.join(root,name)),
    dataform:{projectConfig:{defaultDatabase:'project',vars:{run_id:run}}},
    declare:config=>actions.push({type:'declaration',name:config.name,config,refs:[]}),
    publish:(n,c)=>register('table',n,c), operate:(n,c)=>register('operation',n,c),
    assert:(n,c)=>register('assertion',n,c)
  });
  return actions;
}
const actions=build('r_test');
const get=n=>actions.find(a=>a.name===n && a.type!=='declaration');
nodeAssert.equal(C.fields.length,27);
nodeAssert.equal(new Set(C.fields.map(f=>f.name)).size,27);
nodeAssert.equal(C.maxRejectedRows,0);
nodeAssert.equal(C.mappings.country['México'],'Mexico');
nodeAssert.equal(C.mappings.document_type.Pasaporte,'Passport');
nodeAssert.ok(H.errors(C).includes('TRUNC(SAFE_CAST(credit_score AS BIGNUMERIC))'));
nodeAssert.ok(H.errors(C).includes('estimated_monthly_income.scale'));
nodeAssert.ok(H.errors(C).includes('registration_date.required'));
nodeAssert.ok(!H.errors(C).includes('credit_score.required'));
nodeAssert.ok(get('customers').config.dependencies.includes('customers_publish_gate_r_test'));
nodeAssert.ok(get('customers_publish_gate_r_test').config.dependencies.includes('customers_record_quality_r_test'));
nodeAssert.ok(get('customers_record_quality_r_test').refs.includes('customers_checks_r_test'));
nodeAssert.ok(get('customers').sql.includes('BEGIN TRANSACTION'));
nodeAssert.ok(get('customers').sql.includes('ROLLBACK TRANSACTION'));
nodeAssert.ok(get('customers_input_r_test').sql.includes('AS r FOR SYSTEM_TIME AS OF snapshot_at;'));
nodeAssert.throws(()=>build("bad'; DROP TABLE x"));
nodeAssert.ok(build('preview').find(a=>a.name==='customers_input_preview').sql.includes("ASSERT 'preview' != 'preview'"));
const other=build('r_other');
for(const a of actions.filter(a=>a.config.schema==='bank_stage')) {
  nodeAssert.ok(!other.some(b=>b.name===a.name));
}
const names=new Set(actions.map(a=>a.name));
for(const a of actions) for(const dependency of [...a.refs,...(a.config.dependencies||[])]) {
  nodeAssert.ok(names.has(dependency),`Missing dependency ${dependency}`);
}
console.log('PASS: 27 contract fields, mappings, strict gate, dependency graph, transaction, isolated run tables and run ID validation.');
