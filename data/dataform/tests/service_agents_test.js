// Local graph tests; these do not replace compilation by the Dataform service.
const fs=require('fs');
const vm=require('vm');
const path=require('path');
const nodeAssert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const C=require('../includes/service_agents_contract');
const H=require('../includes/service_agents_helpers');
const source=fs.readFileSync(path.join(root,'definitions/service_agents.js'),'utf8');

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
nodeAssert.equal(C.fields.length,18);
nodeAssert.equal(new Set(C.fields.map(f=>f.name)).size,18);
nodeAssert.deepEqual(C.partialPublicationAllowedErrors,['employee_code.not_unique']);
const errors=H.errors(C);
nodeAssert.ok(errors.includes('employee_code.required'));
nodeAssert.ok(!errors.includes('assigned_branch_id.required'));
nodeAssert.ok(errors.includes('avg_csat.range'));
nodeAssert.ok(errors.includes('total_monthly_interactions.integer'));
const sql=get('service_agents_classified_r_test').sql;
const errorPart=sql.slice(sql.indexOf('ARRAY_CONCAT'),sql.indexOf(') AS _errors'));
nodeAssert.ok(errorPart.includes('agent_id.not_unique'));
nodeAssert.ok(errorPart.includes('employee_code.not_unique'));
nodeAssert.ok(!errorPart.includes('assigned_branch_id'));
nodeAssert.ok(sql.includes('UNRESOLVED'));
nodeAssert.ok(sql.includes('NOT_PROVIDED'));
nodeAssert.ok(!sql.includes('ANY_VALUE'));
nodeAssert.ok(get('service_agents_candidate_r_test').sql.includes('_branch_reference_status, _quality_warnings'));
nodeAssert.ok(get('service_agents').sql.includes('_branch_reference_status,_quality_warnings,_curation_run_id'));
nodeAssert.ok(get('service_agents_checks_r_test').sql.includes('candidate_employee_code_duplicates'));
nodeAssert.ok(get('service_agents_publish_gate_r_test').sql.includes('FROM (SELECT 1 AS singleton)'));
nodeAssert.ok(get('service_agents').config.dependencies.includes('service_agents_publish_gate_r_test'));
nodeAssert.ok(get('service_agents_publish_gate_r_test').config.dependencies.includes('service_agents_record_quality_r_test'));
nodeAssert.ok(get('service_agents').sql.includes('ROLLBACK TRANSACTION'));
nodeAssert.throws(()=>build("bad'; DROP TABLE x"));
const names=new Set(actions.map(a=>a.name));
for(const a of actions) {
 for(const d of [...a.refs,...(a.config.dependencies||[])]) nodeAssert.ok(names.has(d),d);
 if(a.sql) for(const stale of ['undefined','complaint_id','process_date','customer_id','product_id']) nodeAssert.ok(!a.sql.includes(stale),stale);
}
console.log('PASS: service_agents contract, optional branch warning, code quarantine, PK gate, persisted warning metadata and publication transaction.');
