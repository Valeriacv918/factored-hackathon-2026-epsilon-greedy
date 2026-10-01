// Local graph tests; these do not replace compilation by the Dataform service.
const fs=require('fs');
const vm=require('vm');
const path=require('path');
const nodeAssert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const C=require('../includes/daily_exchange_rates_contract');
const H=require('../includes/daily_exchange_rates_helpers');
const source=fs.readFileSync(path.join(root,'definitions/daily_exchange_rates.js'),'utf8');

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
nodeAssert.equal(C.fields.length,7);
nodeAssert.equal(C.maxRejectedRows,0);
nodeAssert.deepEqual(C.primaryKey,['date','source_currency','target_currency']);
nodeAssert.ok(H.normalized({name:'source_currency'}).startsWith('UPPER('));
nodeAssert.equal(H.typed({name:'date',type:'DATE'}),'SAFE_CAST(`date` AS DATE)');
const errors=H.errors(C);
for(const n of ['exchange_rate','buy_rate','sell_rate']) for(const rule of ['scale','precision','positive']) nodeAssert.ok(errors.includes(n+'.'+rule));
nodeAssert.ok(!errors.includes('buy_rate.required'));
const classified=get('daily_exchange_rates_classified_r_test').sql;
nodeAssert.ok(classified.includes('PARTITION BY `date`,source_currency,target_currency'));
nodeAssert.ok(!classified.includes('ANY_VALUE'));
nodeAssert.ok(get('daily_exchange_rates_checks_r_test').sql.includes("rejected<=0,'BLOCK'"));
nodeAssert.ok(get('daily_exchange_rates').config.dependencies.includes('daily_exchange_rates_publish_gate_r_test'));
nodeAssert.ok(get('daily_exchange_rates_publish_gate_r_test').config.dependencies.includes('daily_exchange_rates_record_quality_r_test'));
nodeAssert.ok(get('daily_exchange_rates').sql.includes('ROLLBACK TRANSACTION'));
nodeAssert.throws(()=>build("bad'; DROP TABLE x"));
const names=new Set(actions.map(a=>a.name));
for(const a of actions) {
 for(const d of [...a.refs,...(a.config.dependencies||[])]) nodeAssert.ok(names.has(d),d);
 if(a.sql) for(const stale of ['undefined','branch_id','closing_time','atm_count']) nodeAssert.ok(!a.sql.includes(stale),stale);
}
console.log('PASS: FX composite key, precision, positive rates, optional rates, strict publication gate, quoted date and graph.');
