// Local graph tests; these do not replace compilation by the Dataform service.
const fs=require('fs');
const vm=require('vm');
const path=require('path');
const nodeAssert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const C=require('../includes/complaints_contract');
const H=require('../includes/complaints_helpers');
const source=fs.readFileSync(path.join(root,'definitions/complaints.js'),'utf8');

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
nodeAssert.deepEqual(C.partialPublicationAllowedErrors,['affected_product_id.quarantined_parent']);
const errors=H.errors(C);
nodeAssert.ok(errors.includes('customer_id.required'));
nodeAssert.ok(!errors.includes('affected_product_id.required'));
nodeAssert.ok(errors.includes('resolution_satisfaction.range'));
nodeAssert.ok(errors.includes('resolution_days.integer'));
nodeAssert.ok(!errors.includes('product_owner_mismatch'));
nodeAssert.ok(H.warnings().includes('customer_id.product_owner_mismatch'));
const sql=get('complaints_classified_r_test').sql;
const errorPart=sql.slice(sql.indexOf('ARRAY_CONCAT'),sql.indexOf(') AS _errors'));
nodeAssert.ok(!errorPart.includes('product_owner_mismatch'));
nodeAssert.ok(errorPart.includes('customer_id.foreign_key'));
nodeAssert.ok(errorPart.includes('t.affected_product_id IS NOT NULL'));
nodeAssert.ok(errorPart.includes('affected_product_id.quarantined_parent'));
nodeAssert.ok(sql.includes('THEN CAST(NULL AS BOOL)'));
nodeAssert.ok(get('complaints_candidate_r_test').sql.includes('_product_owner_mismatch, _quality_warnings'));
nodeAssert.ok(get('complaints').sql.includes('${columns}')===false);
nodeAssert.ok(get('complaints').sql.includes('_product_owner_mismatch,_quality_warnings,_curation_run_id'));
nodeAssert.ok(get('complaints').sql.includes('PARTITION BY process_date'));
nodeAssert.ok(get('complaints').sql.includes('ROLLBACK TRANSACTION'));
nodeAssert.ok(get('complaints_publish_gate_r_test').sql.includes('FROM (SELECT 1 AS singleton)'));
nodeAssert.ok(get('complaints').config.dependencies.includes('complaints_publish_gate_r_test'));
nodeAssert.ok(get('complaints_publish_gate_r_test').config.dependencies.includes('complaints_record_quality_r_test'));
nodeAssert.ok(H.normalized({name:'description'},C).endsWith(',NULL,description)'));
nodeAssert.throws(()=>build("bad'; DROP TABLE x"));
const names=new Set(actions.map(a=>a.name));
for(const a of actions) {
 for(const d of [...a.refs,...(a.config.dependencies||[])]) nodeAssert.ok(names.has(d),d);
 if(a.sql) for(const stale of ['undefined','transaction_date','transaction_id','fraud_score']) nodeAssert.ok(!a.sql.includes(stale),stale);
}
console.log('PASS: complaint contract, optional product FK, owner mismatch warning only, nullable owner flag, retained row warnings, publication gate and transaction.');

