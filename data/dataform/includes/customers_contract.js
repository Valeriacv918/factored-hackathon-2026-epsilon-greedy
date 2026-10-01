// Executable curated contract. Raw contract remains independently versioned in GCS.
const fields = [
  ['customer_id','STRING',true,20], ['document_number','STRING',true,20],
  ['document_type','STRING',true,10], ['first_name','STRING',true,100],
  ['last_name','STRING',true,100], ['date_of_birth','DATE',true],
  ['gender','STRING',false,1], ['email','STRING',false,100],
  ['mobile_phone','STRING',false,20], ['landline_phone','STRING',false,20],
  ['address','STRING',false,200], ['city','STRING',true,100],
  ['state','STRING',true,100], ['country','STRING',true,50],
  ['postal_code','STRING',false,10], ['detected_accent','STRING',false,50],
  ['segment','STRING',true,50], ['credit_score','INT64',false],
  ['estimated_monthly_income','NUMERIC',false], ['occupation','STRING',false,100],
  ['marital_status','STRING',false,20], ['education_level','STRING',false,50],
  ['registration_date','TIMESTAMP',true], ['registration_branch_id','STRING',true,20],
  ['customer_status','STRING',true,20], ['last_updated','TIMESTAMP',true],
  ['accepts_marketing','BOOL',true]
].map(([name,type,required,maxLength]) => ({name,type,required,maxLength}));

module.exports = {
  version:'1.0.0', table:'customers', fields,
  mappings: {country:{'México':'Mexico'}, document_type:{'Pasaporte':'Passport'}},
  domains: {
    country:['Mexico','Colombia','Argentina'],
    document_type:['DNI','CURP','CC','CE','Passport'],
    gender:['M','F','O'], detected_accent:['mexican','colombian','argentine','neutral'],
    segment:['Premium','Plus','Basic','Student'],
    customer_status:['Active','Inactive','Suspended','Closed']
  },
  booleanTrue:['true','1','t','yes','y'],
  booleanFalse:['false','0','f','no','n'],
  maxRejectedRows:0,
  duplicatePolicy:'collapse_exact_reject_conflicting_keys',
  pendingRules:['registration_branch_id_foreign_key'],
  observations:['birth_after_registration','last_updated_before_registration'],
  timestampPolicy:'UTC when source has no explicit timezone; preserve raw for review'
};
