module.exports = {
  "version": "1.0.0",
  "table": "branches",
  "fields": [
    {
      "name": "branch_id",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    },
    {
      "name": "branch_code",
      "type": "STRING",
      "required": true,
      "maxLength": 10
    },
    {
      "name": "branch_name",
      "type": "STRING",
      "required": true,
      "maxLength": 100
    },
    {
      "name": "branch_type",
      "type": "STRING",
      "required": true,
      "maxLength": 30
    },
    {
      "name": "address",
      "type": "STRING",
      "required": true,
      "maxLength": 200
    },
    {
      "name": "city",
      "type": "STRING",
      "required": true,
      "maxLength": 100
    },
    {
      "name": "state",
      "type": "STRING",
      "required": true,
      "maxLength": 100
    },
    {
      "name": "country",
      "type": "STRING",
      "required": true,
      "maxLength": 50
    },
    {
      "name": "postal_code",
      "type": "STRING",
      "required": false,
      "maxLength": 10
    },
    {
      "name": "geographic_zone",
      "type": "STRING",
      "required": true,
      "maxLength": 50
    },
    {
      "name": "phone",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    },
    {
      "name": "email",
      "type": "STRING",
      "required": false,
      "maxLength": 100
    },
    {
      "name": "opening_time",
      "type": "TIME",
      "required": true,
      "maxLength": null
    },
    {
      "name": "closing_time",
      "type": "TIME",
      "required": true,
      "maxLength": null
    },
    {
      "name": "has_atms",
      "type": "BOOL",
      "required": true,
      "maxLength": null
    },
    {
      "name": "atm_count",
      "type": "INT64",
      "required": false,
      "maxLength": null
    },
    {
      "name": "has_teller_windows",
      "type": "BOOL",
      "required": true,
      "maxLength": null
    },
    {
      "name": "teller_window_count",
      "type": "INT64",
      "required": false,
      "maxLength": null
    },
    {
      "name": "latitude",
      "type": "NUMERIC",
      "required": false,
      "maxLength": null
    },
    {
      "name": "longitude",
      "type": "NUMERIC",
      "required": false,
      "maxLength": null
    },
    {
      "name": "branch_opening_date",
      "type": "DATE",
      "required": true,
      "maxLength": null
    },
    {
      "name": "branch_status",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    }
  ],
  "mappings": {
    "country": {
      "México": "Mexico"
    },
    "geographic_zone": {
      "Urbana": "Urban"
    }
  },
  "domains": {
    "branch_type": [
      "Main",
      "Express",
      "Premium",
      "Corporate"
    ],
    "geographic_zone": [
      "Urban",
      "Suburban",
      "Rural"
    ],
    "branch_status": [
      "Active",
      "Temporarily Closed",
      "Closed"
    ],
    "country": [
      "Mexico",
      "Colombia",
      "Argentina"
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
  "maxRejectedRows": 0,
  "pendingRules": [],
  "duplicatePolicy": "Reject every repeated branch_id or branch_code; block publication",
  "timePolicy": "Local TIME without date or timezone; preserve schedules; closing<=opening is WARN"
};
