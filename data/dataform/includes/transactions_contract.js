module.exports = {
  "version": "1.0.0",
  "table": "transactions",
  "fields": [
    {
      "name": "transaction_id",
      "type": "STRING",
      "required": true,
      "maxLength": 30
    },
    {
      "name": "transaction_date",
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
      "name": "transaction_type",
      "type": "STRING",
      "required": true,
      "maxLength": 50
    },
    {
      "name": "transaction_category",
      "type": "STRING",
      "required": false,
      "maxLength": 50
    },
    {
      "name": "amount",
      "type": "NUMERIC",
      "required": true,
      "maxLength": null
    },
    {
      "name": "currency",
      "type": "STRING",
      "required": true,
      "maxLength": 3
    },
    {
      "name": "amount_usd",
      "type": "NUMERIC",
      "required": false,
      "maxLength": null
    },
    {
      "name": "channel",
      "type": "STRING",
      "required": true,
      "maxLength": 30
    },
    {
      "name": "branch_id",
      "type": "STRING",
      "required": false,
      "maxLength": 20
    },
    {
      "name": "merchant_name",
      "type": "STRING",
      "required": false,
      "maxLength": 150
    },
    {
      "name": "merchant_category",
      "type": "STRING",
      "required": false,
      "maxLength": 50
    },
    {
      "name": "transaction_country",
      "type": "STRING",
      "required": true,
      "maxLength": 50
    },
    {
      "name": "transaction_city",
      "type": "STRING",
      "required": false,
      "maxLength": 100
    },
    {
      "name": "transaction_status",
      "type": "STRING",
      "required": true,
      "maxLength": 20
    },
    {
      "name": "response_code",
      "type": "STRING",
      "required": false,
      "maxLength": 10
    },
    {
      "name": "is_fraud",
      "type": "BOOL",
      "required": true,
      "maxLength": null
    },
    {
      "name": "fraud_score",
      "type": "NUMERIC",
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
    }
  ],
  "mappings": {
    "transaction_country": {
      "México": "Mexico"
    }
  },
  "domains": {
    "transaction_type": [
      "Deposit",
      "Withdrawal",
      "Transfer",
      "Payment",
      "Purchase",
      "Adjustment"
    ],
    "transaction_category": [
      "Food",
      "Transport",
      "Services",
      "Entertainment",
      "Health",
      "Other"
    ],
    "channel": [
      "ATM",
      "Branch",
      "Web",
      "App",
      "POS",
      "Transfer"
    ],
    "transaction_status": [
      "Approved",
      "Declined",
      "Pending",
      "Reversed"
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
    "product_id.quarantined_parent"
  ],
  "pendingRules": [
    "branch_id_foreign_key",
    "currency_dictionary",
    "source_timezone_confirmation"
  ],
  "timestampPolicy": "Timezone difference is a working hypothesis, not verified. No offset correction. BigQuery parses zone-free timestamps as UTC; preserve process_date.",
  "duplicatePolicy": "Reject all repeated transaction IDs and block publication",
  "publicationPolicy": "Partial only for quarantined parent products; any other row error blocks"
};
