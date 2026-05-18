import csv
import io

from django.core.exceptions import ValidationError

REQUIRED_HEADERS = ('name', 'address')
OPTIONAL_HEADERS = ('phone',)
ALL_KNOWN_HEADERS = REQUIRED_HEADERS + OPTIONAL_HEADERS
MAX_ROWS = 20


def parse_and_validate(uploaded_file):
    """
    Read the UploadedFile, validate, and return list[dict] of hospital rows.
    Raises django.core.exceptions.ValidationError with a descriptive message on failure.
    """
    try:
        raw = uploaded_file.read().decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValidationError(f'File must be UTF-8 encoded text: {exc}')
    finally:
        uploaded_file.seek(0)

    reader = csv.DictReader(io.StringIO(raw))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]

    missing = [h for h in REQUIRED_HEADERS if h not in headers]
    if missing:
        raise ValidationError(
            f'Missing required column(s): {", ".join(missing)}. '
            f'Required: {", ".join(REQUIRED_HEADERS)}.'
        )

    rows = []
    for index, raw_row in enumerate(reader, start=2):  # start=2 → header is row 1
        row = {key: (value or '').strip() for key, value in raw_row.items() if key}
        if not row.get('name'):
            raise ValidationError(f'Row {index}: "name" is required.')
        if not row.get('address'):
            raise ValidationError(f'Row {index}: "address" is required.')
        rows.append({
            'name': row['name'],
            'address': row['address'],
            'phone': row.get('phone') or '',
        })

    if not rows:
        raise ValidationError('CSV contains no hospital rows.')
    if len(rows) > MAX_ROWS:
        raise ValidationError(f'CSV contains {len(rows)} rows; maximum is {MAX_ROWS}.')

    return rows
