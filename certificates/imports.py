import csv
import datetime
import io
import re

import openpyxl

_HEADER_KEYWORDS = {
    'student_name': ['nome'],
    'cpf': ['cpf'],
    'subject_code': ['assunto', 'codigo', 'código'],
    'course_date': ['data'],
}

_DATE_FORMATS = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']


def _match_header(cell_text):
    text = (cell_text or '').strip().lower()
    for field, keywords in _HEADER_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return field
    return None


def _parse_date(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.date() if isinstance(value, datetime.datetime) else value
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _read_rows(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith('.csv'):
        text = uploaded_file.read().decode('utf-8-sig', errors='replace')
        reader = csv.reader(io.StringIO(text))
        return list(reader)

    workbook = openpyxl.load_workbook(uploaded_file, data_only=True, read_only=True)
    sheet = workbook.worksheets[0]
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def parse_spreadsheet(uploaded_file):
    """Returns (rows, error). rows is a list of dicts with student_name/cpf/subject_code/course_date
    (parsed) plus 'status' ('ok'/'error') and 'error_msg'. error is a top-level message (e.g. no
    recognizable header) or None."""
    raw_rows = _read_rows(uploaded_file)
    if not raw_rows:
        return [], 'A planilha está vazia.'

    header = raw_rows[0]
    column_map = {i: _match_header(cell) for i, cell in enumerate(header)}
    if not any(column_map.values()):
        return [], 'Não foi possível identificar as colunas Nome, CPF, Assunto ou Data no cabeçalho.'

    rows = []
    for raw_row in raw_rows[1:]:
        if not any(cell not in (None, '') for cell in raw_row):
            continue
        data = {}
        for i, field in column_map.items():
            if field and i < len(raw_row):
                data[field] = raw_row[i]

        student_name = str(data.get('student_name', '') or '').strip()
        cpf_digits = re.sub(r'\D', '', str(data.get('cpf', '') or ''))
        subject_code = re.sub(r'\D', '', str(data.get('subject_code', '') or ''))
        course_date = _parse_date(data.get('course_date')) if data.get('course_date') else None

        errors = []
        if not student_name:
            errors.append('nome ausente')
        if len(cpf_digits) != 11:
            errors.append('CPF inválido')
        if len(subject_code) != 9:
            errors.append('assunto inválido')
        if not course_date:
            errors.append('data inválida')

        rows.append({
            'student_name': student_name,
            'cpf': cpf_digits,
            'subject_code': subject_code,
            'course_date': course_date,
            'status': 'ok' if not errors else 'error',
            'error_msg': ', '.join(errors),
        })

    return rows, None
