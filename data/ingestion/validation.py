"""Structural CSV contracts. No cloud dependencies; never log row contents."""
import csv
import hashlib
import json
import re


class ContractError(ValueError):
    def __init__(self, rule, details):
        super().__init__(rule)
        self.rule, self.details = rule, details


def parse_contract(raw):
    contract = json.loads(raw.decode('utf-8-sig'))
    columns = contract.get('columns', [])
    if (not columns or not all(isinstance(c, str) and
            re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,299}', c) for c in columns)
            or len({c.lower() for c in columns}) != len(columns)):
        raise ContractError('contract_columns', {'reason': 'missing, invalid or duplicate columns'})
    if contract.get('raw_type') != 'STRING' or contract.get('nullable') is not True:
        raise ContractError('contract_types', {'required': 'nullable STRING'})
    if contract.get('encoding') not in ('utf-8', 'utf-8-sig'):
        raise ContractError('contract_encoding', {'required': 'UTF-8'})
    for key in ('delimiter', 'quotechar'):
        value = contract.get(key)
        if not isinstance(value, str) or len(value) != 1 or len(value.encode()) != 1:
            raise ContractError('contract_csv_options', {'field': key})
    if contract['delimiter'] == contract['quotechar']:
        raise ContractError('contract_csv_options', {'reason': 'delimiter equals quote'})
    if not isinstance(contract.get('version'), str) or not contract.get('table'):
        raise ContractError('contract_identity', {'reason': 'version and table required'})
    return contract, hashlib.sha256(raw).hexdigest()


def validate_csv(stream, contract):
    reader = csv.reader(stream, delimiter=contract['delimiter'],
                        quotechar=contract['quotechar'], strict=True)
    count = 0
    csv.field_size_limit(10 * 1024 * 1024)
    try:
        header = next(reader, None)
        if header != contract['columns']:
            # Do not copy unexpected header text into logs: it might contain data.
            raise ContractError('header', {
                'expected_columns': len(contract['columns']),
                'actual_columns': len(header) if header is not None else 0,
                'reason': 'names or order differ'})
        for row in reader:
            if len(row) != len(header):
                raise ContractError('row_width', {
                    'record': count + 1, 'line_end': reader.line_num,
                    'expected': len(header), 'actual': len(row)})
            if any('\x00' in value for value in row):
                raise ContractError('null_character', {'record': count + 1})
            count += 1
    except (UnicodeError, csv.Error) as exc:
        raise ContractError('csv_syntax_or_encoding', {
            'record': count + 1, 'error_type': type(exc).__name__}) from None
    return count
