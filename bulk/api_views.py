"""
JSON API for hospital bulk processing — matches the assignment spec.

Endpoints (mounted at /hospitals/bulk... in paribus/urls.py):
    POST   /hospitals/bulk                       — submit CSV, queue batch
    GET    /hospitals/bulk/<batch_id>            — status for a batch (spec response shape)
    POST   /hospitals/bulk/validate              — pre-flight CSV validation
    POST   /hospitals/bulk/<batch_id>/resume     — retry just the failed rows

The HTML upload flow at /  is unchanged.
"""
import uuid

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .constant import MAX_UPLOAD_BYTES
from .services.csv_parser import parse_and_validate
from .services.hospital_api import (
    activate_batch,
    delete_hospitals_by_batch,
    list_hospitals_by_batch,
)
from .tasks import (
    batch_cache_key,
    make_initial_state,
    process_batch,
    retry_failed_rows,
)


def _bad_request(message, **extra):
    body = {'error': message}
    body.update(extra)
    return JsonResponse(body, status=400)


def _not_found(message):
    return JsonResponse({'error': message}, status=404)


def _extract_csv(request):
    """Return (uploaded_file, error_response_or_None)."""
    uploaded = request.FILES.get('file') or request.FILES.get('csv')
    if uploaded is None:
        return None, _bad_request(
            "Missing CSV. Send the file as multipart form-data under field name 'file' (or 'csv').",
        )
    if uploaded.size > MAX_UPLOAD_BYTES:
        return None, _bad_request(
            f'File too large ({uploaded.size} bytes). Max is {MAX_UPLOAD_BYTES} bytes.',
        )
    if not (uploaded.name or '').lower().endswith('.csv'):
        return None, _bad_request('File must have a .csv extension.')
    return uploaded, None


def _public_state(state):
    """Strip internal fields before returning to clients."""
    return {k: v for k, v in state.items() if not k.startswith('_')}


@method_decorator(csrf_exempt, name='dispatch')
class BulkUploadAPIView(View):
    """POST /hospitals/bulk — queue a batch for processing. Returns 202 + batch_id."""

    def post(self, request):
        uploaded, err = _extract_csv(request)
        if err:
            return err
        try:
            rows = parse_and_validate(uploaded)
        except ValidationError as exc:
            return _bad_request('CSV validation failed.', details=list(exc.messages))

        batch_id = str(uuid.uuid4())
        state = make_initial_state(batch_id, rows)
        cache.set(batch_cache_key(batch_id), state, timeout=60 * 60 * 24)

        process_batch.delay(batch_id, rows)

        return JsonResponse(
            {
                'batch_id': batch_id,
                'total_hospitals': len(rows),
                'status': 'queued',
                'status_url': reverse('bulk_api:status', args=[batch_id]),
            },
            status=202,
        )


class BulkStatusAPIView(View):
    """GET /hospitals/bulk/<batch_id> — current state in the spec response shape."""

    def get(self, request, batch_id):
        state = cache.get(batch_cache_key(batch_id))
        if not state:
            return _not_found(f'No batch with id {batch_id}.')
        return JsonResponse(_public_state(state), status=200)


@method_decorator(csrf_exempt, name='dispatch')
class BulkValidateAPIView(View):
    """POST /hospitals/bulk/validate — parse and validate CSV without processing."""

    def post(self, request):
        uploaded, err = _extract_csv(request)
        if err:
            return err
        try:
            rows = parse_and_validate(uploaded)
        except ValidationError as exc:
            return JsonResponse(
                {'valid': False, 'errors': list(exc.messages)},
                status=400,
            )
        return JsonResponse(
            {
                'valid': True,
                'total_hospitals': len(rows),
                'preview': rows[:3],
            },
            status=200,
        )


def _proxy_response(result, success_status=200, success_payload=None):
    """Translate the service-layer result dict into an HTTP response."""
    if result['ok']:
        body = success_payload if success_payload is not None else (result.get('data') or {})
        return JsonResponse(body, status=success_status, safe=False)
    return JsonResponse(
        {'error': result.get('error'), 'upstream_status': result.get('status')},
        status=result.get('status') or 502,
    )


@method_decorator(csrf_exempt, name='dispatch')
class BatchHospitalsAPIView(View):
    """
    GET    /hospitals/batch/<batch_id>  — list hospitals in the batch
    DELETE /hospitals/batch/<batch_id>  — delete all hospitals in the batch
    """

    def get(self, request, batch_id):
        return _proxy_response(list_hospitals_by_batch(batch_id))

    def delete(self, request, batch_id):
        result = delete_hospitals_by_batch(batch_id)
        if result['ok']:
            # Invalidate locally cached batch state so a subsequent status call
            # doesn't return stale per-row info for a now-deleted batch.
            cache.delete(batch_cache_key(str(batch_id)))
        return _proxy_response(result, success_payload={'deleted': True, 'batch_id': str(batch_id)})


@method_decorator(csrf_exempt, name='dispatch')
class BatchActivateAPIView(View):
    """PATCH /hospitals/batch/<batch_id>/activate — activate all hospitals in the batch."""

    def patch(self, request, batch_id):
        result = activate_batch(batch_id)
        if result['ok']:
            # Keep local state honest if this batch was originally created via /hospitals/bulk.
            state = cache.get(batch_cache_key(str(batch_id)))
            if state:
                state['batch_activated'] = True
                for entry in state.get('hospitals', []):
                    if entry['status'] == 'created':
                        entry['status'] = 'created_and_activated'
                cache.set(batch_cache_key(str(batch_id)), state, timeout=60 * 60 * 24)
        return _proxy_response(result, success_payload={'activated': True, 'batch_id': str(batch_id)})


@method_decorator(csrf_exempt, name='dispatch')
class BulkResumeAPIView(View):
    """POST /hospitals/bulk/<batch_id>/resume — retry failed rows then re-activate."""

    def post(self, request, batch_id):
        state = cache.get(batch_cache_key(batch_id))
        if not state:
            return _not_found(f'No batch with id {batch_id}.')
        if state.get('status') == 'in_progress':
            return JsonResponse(
                {'error': 'Batch is still in progress.', 'state': _public_state(state)},
                status=409,
            )
        failed_entries = [h for h in state['hospitals'] if h['status'] == 'failed']
        if not failed_entries:
            return JsonResponse(
                {'message': 'Nothing to resume; no failed rows.', 'state': _public_state(state)},
                status=200,
            )
        rows_to_retry = state.get('_rows_by_index')
        if not rows_to_retry:
            return JsonResponse(
                {'error': 'Original row data not available for this batch (TTL expired).'},
                status=410,
            )
        retry_payload = [
            {'row': h['row'], **rows_to_retry[str(h['row'])]}
            for h in failed_entries
        ]
        retry_failed_rows.delay(batch_id, retry_payload)
        return JsonResponse(
            {'message': f'Resuming {len(retry_payload)} failed row(s).', 'batch_id': batch_id},
            status=202,
        )
