// Local graph tests; these do not replace compilation by the Dataform service.
const fs=require('fs');
const vm=require('vm');
const path=require('path');
const nodeAssert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const C=require('../includes/branches_contract');
const H=require('../includes/branches_helpers');
const source=fs.readFileSync(path.join(root,'definitions/branches.js'),'utf8');

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
nodeAssert.equal(C.mappings.geographic_zone.Urbana,'Urban');
nodeAssert.equal(C.mappings.country['México'],'Mexico');
nodeAssert.equal(C.maxRejectedRows,0);
nodeAssert.ok(C.domains.branch_status.includes('Temporarily Closed'));
const errors=H.errors(C);
for(const code of ['branch_code.required','atm_count.integer','atm_count.nonnegative','latitude.scale','longitude.range']) nodeAssert.ok(errors.includes(code));
nodeAssert.ok(!errors.includes('credit_score'));
nodeAssert.ok(!get('branches_classified_r_test').sql.includes('ANY_VALUE'));
nodeAssert.ok(get('branches_classified_r_test').sql.includes('PARTITION BY branch_code'));
nodeAssert.ok(get('branches_checks_r_test').sql.includes("rejected<=0,'BLOCK'"));
nodeAssert.ok(get('branches').config.dependencies.includes('branches_publish_gate_r_test'));
nodeAssert.ok(get('branches_publish_gate_r_test').config.dependencies.includes('branches_record_quality_r_test'));
nodeAssert.ok(get('branches').sql.includes('ROLLBACK TRANSACTION'));
nodeAssert.throws(()=>build("bad'; DROP TABLE x"));
const names=new Set(actions.map(a=>a.name));
for(const a of actions) {
 for(const d of [...a.refs,...(a.config.dependencies||[])]) nodeAssert.ok(names.has(d));
 if(a.sql) for(const stale of ['undefined','date_of_birth','registration_date']) nodeAssert.ok(!a.sql.includes(stale));
}
console.log('PASS: branches fields, mappings, strict rejection policy, unique keys, numeric rules and publication dependencies.');
