// Local graph tests; these do not replace compilation by the Dataform service.
const fs=require('fs');
const vm=require('vm');
const path=require('path');
const nodeAssert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const C=require('../includes/transactions_contract');
const H=require('../includes/transactions_helpers');
const source=fs.readFileSync(path.join(root,'definitions/transactions.js'),'utf8');

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
nodeAssert.equal(C.fields.length,22);
nodeAssert.equal(new Set(C.fields.map(f=>f.name)).size,22);
nodeAssert.deepEqual(C.partialPublicationAllowedErrors,['product_id.quarantined_parent']);
nodeAssert.equal(C.mappings.transaction_country['México'],'Mexico');
const errors=H.errors(C);
for(const rule of ['customer_id.required','product_id.required','amount.scale','fraud_score.range','latitude.scale','longitude.range']) nodeAssert.ok(errors.includes(rule));
for(const rule of ['credit_score','current_balance','last_updated']) nodeAssert.ok(!errors.includes(rule));
nodeAssert.ok(get('transactions').config.dependencies.includes('transactions_publish_gate_r_test'));
nodeAssert.ok(get('transactions_publish_gate_r_test').config.dependencies.includes('transactions_record_quality_r_test'));
nodeAssert.ok(get('transactions_publish_gate_r_test').sql.includes('quarantine_reconciliation'));
nodeAssert.ok(get('transactions_publish_gate_r_test').sql.includes("SELECT 'quarantine_reconciliation'\nFROM (SELECT 1 AS singleton)\nWHERE"));
const classified=get('transactions_classified_r_test').sql;
nodeAssert.ok(classified.includes('customer_id.product_owner_mismatch'));
nodeAssert.ok(classified.includes("['product_id.quarantined_parent'],['product_id.foreign_key']"));
nodeAssert.ok(classified.includes('COUNT(*) OVER(PARTITION BY transaction_id)'));
nodeAssert.ok(!classified.includes('ANY_VALUE'));
nodeAssert.ok(get('transactions').sql.includes('PARTITION BY process_date CLUSTER BY product_id,customer_id'));
nodeAssert.ok(get('transactions').sql.includes('ROLLBACK TRANSACTION'));
nodeAssert.ok(get('transactions').sql.includes('SUCCEEDED_WITH_REJECTIONS'));
nodeAssert.ok(get('transactions_checks_r_test').sql.includes('unapproved_rejections'));
const input=get('transactions_input_r_test').sql;
for(const table of ['bank_curated.customers','bank_curated.products','bank_quarantine.products_rejected','bank_ops.curation_references']) nodeAssert.ok(input.includes(table));
nodeAssert.ok(!input.includes('bank_curated.transactions'));
nodeAssert.throws(()=>build("bad'; DROP TABLE x"));
const names=new Set(actions.map(a=>a.name));
for(const a of actions) for(const d of [...a.refs,...(a.config.dependencies||[])]) nodeAssert.ok(names.has(d),d);
for(const a of actions) if(a.sql) {
 nodeAssert.ok(!a.sql.includes('undefined'));
 nodeAssert.ok(!a.sql.includes('product_number'));
 nodeAssert.ok(!a.sql.includes('DATE_ADD'));
}
console.log('PASS: 22 fields, parent quarantine allowlist, FK and owner checks, partitioning, publication gate, quarantine reconciliation, audit lineage, transaction and run ID guards.');
