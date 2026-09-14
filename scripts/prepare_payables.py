"""Read an original XLSX export and prepare a private, lossless JSON import file."""
import argparse
import hashlib
import json
from pathlib import Path
import openpyxl

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input')
    parser.add_argument('output')
    args = parser.parse_args()
    source = Path(args.input)
    workbook = openpyxl.load_workbook(source, read_only=True, data_only=False)
    if len(workbook.worksheets) != 1:
        raise ValueError('Esperada uma única aba no arquivo de origem.')
    sheet = workbook.active
    values = list(sheet.values)
    headers = list(values[0])
    if len(set(headers)) != len(headers) or any(not h for h in headers):
        raise ValueError('Cabeçalhos vazios ou repetidos.')
    rows = []
    for index, row in enumerate(values[1:], 2):
        if not any(value is not None for value in row):
            continue
        if any(isinstance(v, str) and v.startswith('=') for v in row):
            raise ValueError(f'Fórmula não suportada na linha {index}.')
        rows.append({'row': index, 'values': dict(zip(headers, row))})
    payload = {'format': 'payables-export-v1', 'file': source.name,
               'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'sheet': sheet.title, 'rows': rows}
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(rows)} linhas preparadas. Arquivo original preservado.')

if __name__ == '__main__':
    main()
