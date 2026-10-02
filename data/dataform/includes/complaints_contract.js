module.exports = {
  "version": "1.0.0",
  "table": "complaints",
  "fields": [
    {
      "name": "complaint_id",
      "type": "STRING",
      "required": true,
      "maxLength": 30
    },
    {
      "name": "creation_date",
      "type": "TIMESTAMP",
      "required": true,
      "maxLength": null
    },
    {
      "name": "process_date",
      "type": "DATE",
      "required": true,
      "maxLength": null
    },
    {
      "name": "customer_id",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    },
    {
      "name": "case_type",
      "type": "STRING",
      "required": true,
      "maxLength": 30
    },
    {
      "name": "category",
      "type": "STRING",
      "required": true,
      "maxLength": 100
    },
    {
      "name": "subcategory",
      "type": "STRING",
      "required": false,
      "maxLength": 100
    },
    {
      "name": "reception_channel",
      "type": "STRING",
      "required": true,
      "maxLength": 30
    },
    {
      "name": "affected_product_id",
      "type": "STRING",
      "required": false,
      "maxLength": 20
    },
    {
      "name": "related_branch_id",
      "type": "STRING",
      "required": false,
      "maxLength": 20
    },
    {
      "name": "origin_interaction_id",
      "type": "STRING",
      "required": false,
      "maxLength": 30
    },
    {
      "name": "description",
      "type": "STRING",
      "required": true,
      "maxLength": null
    },
    {
      "name": "claimed_amount",
      "type": "NUMERIC",
      "required": false,
      "maxLength": null
    },
    {
      "name": "currency",
      "type": "STRING",
      "required": false,
      "maxLength": 3
    },
    {
      "name": "priority",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    },
    {
      "name": "status",
      "type": "STRING",
      "required": true,
      "maxLength": 30
    },
    {
      "name": "assigned_agent_id",
      "type": "STRING",
      "required": false,
      "maxLength": 20
    },
    {
      "name": "assignment_date",
      "type": "TIMESTAMP",
      "required": false,
      "maxLength": null
    },
    {
      "name": "first_response_date",
      "type": "TIMESTAMP",
      "required": false,
      "maxLength": null
    },
    {
      "name": "resolution_date",
      "type": "TIMESTAMP",
      "required": false,
      "maxLength": null
    },
    {
      "name": "closing_date",
      "type": "TIMESTAMP",
      "required": false,
      "maxLength": null
    },
    {
      "name": "sla_breached",
      "type": "BOOL",
      "required": true,
      "maxLength": null
    },
    {
      "name": "resolution_days",
      "type": "INT64",
      "required": false,
      "maxLength": null
    },
    {
      "name": "resolution",
      "type": "STRING",
      "required": false,
      "maxLength": null
    },
    {
      "name": "compensation_granted",
      "type": "NUMERIC",
      "required": false,
      "maxLength": null
    },
    {
      "name": "resolution_satisfaction",
      "type": "INT64",
      "required": false,
      "maxLength": null
    },
    {
      "name": "is_repeat_complainer",
      "type": "BOOL",
      "required": true,
      "maxLength": null
    }
  ],
  "mappings": {},
  "domains": {
    "case_type": [
      "Complaint",
      "Claim",
      "Request",
      "Suggestion"
    ],
    "reception_channel": [
      "Call Center",
      "Email",
      "Web",
      "App",
      "Branch",
      "Regulator"
    ],
    "priority": [
      "Low",
      "Medium",
      "High",
      "Critical"
    ],
    "status": [
      "Open",
      "In Process",
      "Escalated",
      "Resolved",
      "Closed",
      "Rejected"
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
    "affected_product_id.quarantined_parent"
  ],
  "pendingRules": [
    "related_branch_id_foreign_key",
    "assigned_agent_id_foreign_key",
    "origin_interaction_id_foreign_key",
    "currency_dictionary",
    "source_timezone_confirmation",
    "SLA_definition"
  ],
  "timestampPolicy": "Preserve dates; timezone difference is an unverified hypothesis. No offset correction; zone-free timestamps parsed as UTC.",
  "ownerPolicy": "Mismatch is WARN, never establishes ownership or authorizes product access.",
  "textPolicy": "Preserve nonblank description and resolution exactly; whitespace-only becomes NULL.",
  "duplicatePolicy": "Reject every repeated complaint_id; block publication",
  "warningRules": [
    "customer_id.product_owner_mismatch",
    "process_date.before_creation_date",
    "currency.missing_with_amount",
    "currency.differs_from_product",
    "resolution_days.negative",
    "claimed_amount.negative",
    "compensation_granted.negative",
    "closing_date.before_resolution",
    "resolution_days.calendar_difference",
    "assignment_date.before_creation",
    "first_response_date.before_creation",
    "resolution_date.before_creation",
    "closing_date.before_creation"
  ]
};
