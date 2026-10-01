module.exports = {
  "version": "1.0.0",
  "table": "daily_exchange_rates",
  "fields": [
    {
      "name": "date",
      "type": "DATE",
      "required": true,
      "maxLength": null
    },
    {
      "name": "source_currency",
      "type": "STRING",
      "required": true,
      "maxLength": 3
    },
    {
      "name": "target_currency",
      "type": "STRING",
      "required": true,
      "maxLength": 3
    },
    {
      "name": "exchange_rate",
      "type": "NUMERIC",
      "required": true,
      "maxLength": null
    },
    {
      "name": "buy_rate",
      "type": "NUMERIC",
      "required": false,
      "maxLength": null
    },
    {
      "name": "sell_rate",
      "type": "NUMERIC",
      "required": false,
      "maxLength": null
    },
    {
      "name": "source",
      "type": "STRING",
      "required": false,
      "maxLength": 50
    }
  ],
  "maxRejectedRows": 0,
  "pendingRules": [
    "quotation_convention",
    "required_date_coverage"
  ],
  "primaryKey": [
    "date",
    "source_currency",
    "target_currency"
  ],
  "ratePolicy": "Positive DECIMAL(12,6); no rounding, inversion, forward fill or rate synthesis",
  "currencyPolicy": "Trim and uppercase; require three ASCII letters; no inferred authoritative currency catalog",
  "sourcePolicy": "Preserve source; do not rank providers or use source to resolve duplicate keys"
};
