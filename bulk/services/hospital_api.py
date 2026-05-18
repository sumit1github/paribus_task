import requests
from django.conf import settings


def _base_url():
    return settings.HOSPITAL_API_BASE_URL.rstrip('/')


def _timeout():
    return getattr(settings, 'HOSPITAL_API_TIMEOUT_SECONDS', 15)


def _url(path):
    return f"{_base_url()}{path}"


def _ok(response, data=None):
    return {'ok': True, 'status': response.status_code, 'error': None, 'data': data}


def _fail(response=None, error=None):
    return {
        'ok': False,
        'status': response.status_code if response is not None else None,
        'error': error or (f'HTTP {response.status_code}: {response.text[:200]}' if response is not None else 'Unknown error'),
        'data': None,
    }


def _parse_json(response):
    try:
        return response.json()
    except ValueError:
        return None


def list_hospitals():
    try:
        response = requests.get(_url('/hospitals/'), timeout=_timeout())
    except requests.RequestException as exc:
        return _fail(error=f'Request failed: {exc}')
    if 200 <= response.status_code < 300:
        return _ok(response, _parse_json(response) or [])
    return _fail(response)


def get_hospital(hospital_id):
    try:
        response = requests.get(_url(f'/hospitals/{hospital_id}'), timeout=_timeout())
    except requests.RequestException as exc:
        return _fail(error=f'Request failed: {exc}')
    if 200 <= response.status_code < 300:
        return _ok(response, _parse_json(response))
    return _fail(response)


def update_hospital(hospital_id, data):
    payload = {k: v for k, v in {
        'name': data.get('name'),
        'address': data.get('address'),
        'phone': data.get('phone') or None,
    }.items() if v is not None}
    try:
        response = requests.put(_url(f'/hospitals/{hospital_id}'), json=payload, timeout=_timeout())
    except requests.RequestException as exc:
        return _fail(error=f'Request failed: {exc}')
    if 200 <= response.status_code < 300:
        return _ok(response, _parse_json(response))
    return _fail(response)


def delete_hospital(hospital_id):
    try:
        response = requests.delete(_url(f'/hospitals/{hospital_id}'), timeout=_timeout())
    except requests.RequestException as exc:
        return _fail(error=f'Request failed: {exc}')
    if 200 <= response.status_code < 300:
        return _ok(response)
    return _fail(response)


def create_hospital(row, batch_id=None):
    """
    POST /hospitals/. Returns dict {ok, status, error, data}.
    Catches request errors so the Celery task can keep going on per-row failure.
    """
    payload = {
        'name': row['name'],
        'address': row['address'],
    }
    if batch_id is not None:
        payload['creation_batch_id'] = str(batch_id)
    phone = row.get('phone') or ''
    if phone:
        payload['phone'] = phone

    try:
        response = requests.post(_url('/hospitals/'), json=payload, timeout=_timeout())
    except requests.RequestException as exc:
        return _fail(error=f'Request failed: {exc}')

    if 200 <= response.status_code < 300:
        return _ok(response, _parse_json(response))
    return _fail(response)


def list_hospitals_by_batch(batch_id):
    try:
        response = requests.get(_url(f'/hospitals/batch/{batch_id}'), timeout=_timeout())
    except requests.RequestException as exc:
        return _fail(error=f'Request failed: {exc}')
    if 200 <= response.status_code < 300:
        return _ok(response, _parse_json(response) or [])
    return _fail(response)


def delete_hospitals_by_batch(batch_id):
    try:
        response = requests.delete(_url(f'/hospitals/batch/{batch_id}'), timeout=_timeout())
    except requests.RequestException as exc:
        return _fail(error=f'Request failed: {exc}')
    if 200 <= response.status_code < 300:
        return _ok(response)
    return _fail(response)


def activate_batch(batch_id):
    """
    PATCH /hospitals/batch/{batch_id}/activate. No body, empty success response.
    Returns dict {ok, status, error}.
    """
    try:
        response = requests.patch(
            _url(f'/hospitals/batch/{batch_id}/activate'),
            timeout=_timeout(),
        )
    except requests.RequestException as exc:
        return _fail(error=f'Request failed: {exc}')

    if 200 <= response.status_code < 300:
        return _ok(response)
    return _fail(response)
