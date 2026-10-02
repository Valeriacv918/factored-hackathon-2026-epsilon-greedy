module.exports = {
  "version": "1.0.0",
  "table": "products",
  "fields": [
    {
      "name": "product_id",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    },
    {
      "name": "customer_id",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    },
    {
      "name": "product_type",
      "type": "STRING",
      "required": true,
      "maxLength": 50
    },
    {
      "name": "product_number",
      "type": "STRING",
      "required": true,
      "maxLength": 30
    },
    {
      "name": "currency",
      "type": "STRING",
      "required": true,
      "maxLength": 3
    },
    {
      "name": "current_balance",
      "type": "NUMERIC",
      "required": true,
      "maxLength": null
    },
    {
      "name": "credit_limit",
      "type": "NUMERIC",
      "required": false,
      "maxLength": null
    },
    {
      "name": "interest_rate",
      "type": "NUMERIC",
      "required": false,
      "maxLength": null
    },
    {
      "name": "opening_date",
      "type": "DATE",
      "required": true,
      "maxLength": null
    },
    {
      "name": "expiration_date",
      "type": "DATE",
      "required": false,
      "maxLength": null
    },
    {
      "name": "opening_branch_id",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    },
    {
      "name": "product_status",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    },
    {
      "name": "opening_channel",
      "type": "STRING",
      "required": true,
      "maxLength": 30
    },
    {
      "name": "has_linked_app",
      "type": "BOOL",
      "required": true,
      "maxLength": null
    },
    {
      "name": "days_past_due",
      "type": "INT64",
      "required": false,
      "maxLength": null
    },
    {
      "name": "last_transaction_date",
      "type": "TIMESTAMP",
      "required": false,
      "maxLength": null
    },
    {
      "name": "last_updated",
      "type": "TIMESTAMP",
      "required": true,
      "maxLength": null
    }
  ],
  "mappings": {},
  "domains": {
    "product_type": [
      "Cuenta Ahorro",
      "Cuenta Corriente",
      "Tarjeta Crédito",
      "Tarjeta Débito",
      "Préstamo Personal",
      "Préstamo Hipotecario",
      "Inversión",
      "Seguro"
    ],
    "currency": [
      "MXN",
      "COP",
      "ARS",
      "USD"
    ],
    "product_status": [
      "Active",
      "Blocked",
      "Closed",
      "Suspended"
    ],
    "opening_channel": [
      "Branch",
      "Web",
      "App",
      "Call Center"
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
  "pendingRules": [
    "opening_branch_id_foreign_key"
  ],
  "partialPublicationAllowedErrors": [
    "duplicate_product_number"
  ],
  "duplicatePolicy": "quarantine_every_row_in_repeated_number_groups",
  "domainPolicy": "Preserve observed Spanish product types",
  "timestampPolicy": "UTC when timezone absent"
};
