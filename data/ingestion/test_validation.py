import io
import json
import unittest
from validation import ContractError, parse_contract, validate_csv

CONTRACT = dict(version='1.0.0', table='customers', encoding='utf-8-sig',
                delimiter=',', quotechar='"', raw_type='STRING', nullable=True,
                columns=['customer_id', 'credit_score'])


class ValidationTests(unittest.TestCase):
    def check(self, text):
        return validate_csv(io.StringIO(text, newline=''), CONTRACT)

    def test_nullable_string_preserved(self):
        self.assertEqual(self.check('customer_id,credit_score\n001,701.0\n002,\n'), 2)

    def test_multiline_field_is_one_record(self):
        self.assertEqual(self.check('customer_id,credit_score\n"a\nb",701.0\n'), 1)

    def test_wrong_order_rejected(self):
        with self.assertRaises(ContractError):
            self.check('credit_score,customer_id\n701,001\n')

    def test_missing_or_extra_field_rejected(self):
        for row in ('001', '001,701,extra'):
            with self.subTest(row=row), self.assertRaises(ContractError):
                self.check('customer_id,credit_score\n' + row + '\n')

    def test_unclosed_quote_rejected(self):
        with self.assertRaises(ContractError):
            self.check('customer_id,credit_score\n"001,701\n')

    def test_null_character_rejected(self):
        with self.assertRaises(ContractError):
            self.check('customer_id,credit_score\n001,7\x0001\n')

    def test_empty_file_rejected(self):
        with self.assertRaises(ContractError):
            self.check('')

    def test_duplicate_contract_columns_rejected(self):
        raw = json.dumps(dict(CONTRACT, columns=['id', 'ID'])).encode()
        with self.assertRaises(ContractError):
            parse_contract(raw)

    def test_contract_hash_tracks_changes(self):
        _, a = parse_contract(json.dumps(CONTRACT).encode())
        _, b = parse_contract(json.dumps(dict(CONTRACT, version='1.0.1')).encode())
        self.assertNotEqual(a, b)


if __name__ == '__main__':
    unittest.main()
