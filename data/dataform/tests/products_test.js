// Local graph tests; these do not replace compilation by the Dataform service.
const fs=require('fs');
const vm=require('vm');
const path=require('path');
const nodeAssert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const C=require('../includes/products_contract');
const H=require('../includes/products_helpers');
const source=fs.readFileSync(path.join(root,'definitions/products.js'),'utf8');

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
nodeAssert.equal(C.fields.length,17);
nodeAssert.equal(new Set(C.fields.map(f=>f.name)).size,17);
nodeAssert.deepEqual(C.partialPublicationAllowedErrors,['duplicate_product_number']);
const errors=H.errors(C);
for(const rule of ['customer_id.required','current_balance.scale','credit_limit.precision','days_past_due.integer']) nodeAssert.ok(errors.includes(rule));
nodeAssert.ok(!errors.includes('credit_score'));
nodeAssert.ok(get('products').config.dependencies.includes('products_publish_gate_r_test'));
nodeAssert.ok(get('products_publish_gate_r_test').config.dependencies.includes('products_record_quality_r_test'));
nodeAssert.ok(get('products').sql.includes('SUCCEEDED_WITH_REJECTIONS'));
nodeAssert.ok(get('products').sql.includes('ROLLBACK TRANSACTION'));
nodeAssert.ok(get('products_classified_r_test').sql.includes('COUNT(*) OVER(PARTITION BY product_number)'));
nodeAssert.ok(!get('products_classified_r_test').sql.includes('ANY_VALUE'));
nodeAssert.ok(get('products_checks_r_test').sql.includes('unapproved_rejections'));
nodeAssert.ok(get('products_input_r_test').sql.includes('bank_curated.customers'));
nodeAssert.ok(get('products_input_r_test').sql.includes('AS r FOR SYSTEM_TIME AS OF snapshot_at'));
nodeAssert.throws(()=>build("bad'; DROP TABLE x"));
const names=new Set(actions.map(a=>a.name));
for(const a of actions) for(const d of [...a.refs,...(a.config.dependencies||[])]) nodeAssert.ok(names.has(d),d);
for(const a of actions) if(a.sql) nodeAssert.ok(!a.sql.includes('undefined'));
console.log('PASS: products contract, dependency gate, quarantine-all duplicate logic, partial-publication allowlist, reference snapshot, transaction and run ID guards. SQL execution requires BigQuery.');
