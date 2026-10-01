module.exports = {
  "version": "1.0.0",
  "table": "service_agents",
  "fields": [
    {
      "name": "agent_id",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    },
    {
      "name": "employee_code",
      "type": "STRING",
      "required": true,
      "maxLength": 15
    },
    {
      "name": "first_name",
      "type": "STRING",
      "required": true,
      "maxLength": 100
    },
    {
      "name": "last_name",
      "type": "STRING",
      "required": true,
      "maxLength": 100
    },
    {
      "name": "email",
      "type": "STRING",
      "required": true,
      "maxLength": 100
    },
    {
      "name": "phone",
      "type": "STRING",
      "required": false,
      "maxLength": 20
    },
    {
      "name": "native_accent",
      "type": "STRING",
      "required": true,
      "maxLength": 50
    },
    {
      "name": "country_of_origin",
      "type": "STRING",
      "required": true,
      "maxLength": 50
    },
    {
      "name": "assigned_branch_id",
      "type": "STRING",
      "required": false,
      "maxLength": 20
    },
    {
      "name": "agent_type",
      "type": "STRING",
      "required": true,
      "maxLength": 30
    },
    {
      "name": "experience_level",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    },
    {
      "name": "languages",
      "type": "STRING",
      "required": true,
      "maxLength": 100
    },
    {
      "name": "specialty",
      "type": "STRING",
      "required": false,
      "maxLength": 100
    },
    {
      "name": "hire_date",
      "type": "DATE",
      "required": true,
      "maxLength": null
    },
    {
      "name": "avg_csat",
      "type": "NUMERIC",
      "required": false,
      "maxLength": null
    },
    {
      "name": "total_monthly_interactions",
      "type": "INT64",
      "required": false,
      "maxLength": null
    },
    {
      "name": "agent_status",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    },
    {
      "name": "work_shift",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    }
  ],
  "mappings": {
    "country_of_origin": {
      "México": "Mexico"
    }
  },
  "domains": {
    "native_accent": [
      "mexican",
      "colombian",
      "argentine"
    ],
    "country_of_origin": [
      "Mexico",
      "Colombia",
      "Argentina"
    ],
    "agent_type": [
      "Phone",
      "In-Person",
      "Digital",
      "Hybrid"
    ],
    "experience_level": [
      "Junior",
      "Mid-Senior",
      "Senior",
      "Specialist"
    ],
    "agent_status": [
      "Active",
      "Vacation",
      "Leave",
      "Inactive"
    ],
    "work_shift": [
      "Morning",
      "Afternoon",
      "Night",
      "Rotating"
    ]
  },
  "booleanTrue": [
    "true",
    "1",
    "t",
    "yes",
    "y"
  ],
  "booleanFalse": [
    "false",
    "0",
    "f",
    "no",
    "n"
  ],
  "partialPublicationAllowedErrors": [
    "employee_code.not_unique"
  ],
  "pendingRules": [
    "assigned_branch_id_foreign_key_exception"
  ],
  "warningRules": [
    "assigned_branch_id.unresolved",
    "assigned_branch_id.branch_not_active"
  ],
  "branchPolicy": "Missing branch is an approved WARN exception; preserve source ID without claiming a resolved relationship.",
  "duplicatePolicy": "Quarantine every row with repeated employee_code; repeated agent_id blocks publication",
  "languagesPolicy": "Preserve languages as text; no splitting or inference"
};
