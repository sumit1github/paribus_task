import logging
import time

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.template.loader import render_to_string

from .services.hospital_api import (
    activate_batch as _upstream_activate_batch,
    create_hospital,
    delete_hospitals_by_batch as _upstream_delete_batch,
)
from bulk.constant import BATCH_GROUP_NAME

logger = logging.getLogger(__name__)


BATCH_STATE_TTL = 60 * 60 * 24  # 24h


def batch_cache_key(batch_id):
    return f'bulk:batch:{batch_id}'


def make_initial_state(batch_id, rows):
    return {
        'batch_id': str(batch_id),
        'total_hospitals': len(rows),
        'processed_hospitals': 0,
        'failed_hospitals': 0,
        'processing_time_seconds': 0,
        'batch_activated': False,
        'status': 'queued',
        'error': None,
        'hospitals': [
            {
                'row': i,
                'hospital_id': None,
                'name': r.get('name'),
                'status': 'pending',
                'error': None,
            }
            for i, r in enumerate(rows, start=1)
        ],
        # Underscore-prefixed: stripped from API responses, used by resume to replay rows.
        '_rows_by_index': {str(i): r for i, r in enumerate(rows, start=1)},
    }


def _save_state(state):
    cache.set(batch_cache_key(state['batch_id']), state, timeout=BATCH_STATE_TTL)


def send_progress(context):
    """
    Render the progress partial with `context` and broadcast it to every
    client subscribed to BATCH_GROUP_NAME. The consumer forwards the HTML
    directly to the browser, which swaps it into #progress-body.
    """
    html = render_to_string('bulk/_progress_body.html', context)
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        BATCH_GROUP_NAME,
        {'type': 'progress.message', 'html': html},
    )


def _progress_context(batch_id, total, processed, failed, status, batch_activated=False, error=None):
    pct = int((processed / total) * 100) if total else 0
    return {
        'batch_id': batch_id,
        'total': total,
        'processed': processed,
        'failed': failed,
        'succeeded': processed - failed,
        'percent': pct,
        'status': status,
        'batch_activated': batch_activated,
        'error': error,
    }


@shared_task(name='bulk.process_batch')
def process_batch(batch_id, rows):
    total = len(rows)
    processed = 0
    failed = 0
    started_at = time.monotonic()

    state = cache.get(batch_cache_key(batch_id)) or make_initial_state(batch_id, rows)
    state['status'] = 'in_progress'
    _save_state(state)

    send_progress(_progress_context(batch_id, total, 0, 0, 'in_progress'))

    for index, row in enumerate(rows, start=1):
        result = create_hospital(row, batch_id)
        processed += 1
        entry = state['hospitals'][index - 1]
        if result['ok']:
            data = result.get('data') or {}
            entry['hospital_id'] = data.get('id')
            entry['status'] = 'created'
            entry['error'] = None
        else:
            failed += 1
            entry['status'] = 'failed'
            entry['error'] = result.get('error')
            logger.warning(
                'Hospital create failed for batch=%s row=%s: %s',
                batch_id, row.get('name'), result.get('error'),
            )
        state['processed_hospitals'] = processed
        state['failed_hospitals'] = failed
        _save_state(state)
        send_progress(_progress_context(batch_id, total, processed, failed, 'in_progress'))

    state['processing_time_seconds'] = round(time.monotonic() - started_at, 2)
    state['status'] = 'complete'
    state['error'] = None
    _save_state(state)

    send_progress(
        _progress_context(
            batch_id, total, processed, failed,
            status='complete',
        ),
    )
    return {
        'batch_id': batch_id,
        'total': total,
        'processed': processed,
        'failed': failed,
    }


@shared_task(name='bulk.activate_batch_async')
def activate_batch_async(batch_id):
    """
    Activate every hospital in a batch via the upstream PATCH endpoint.
    Updates locally cached batch state (if any) so the JSON status reflects activation.
    """
    batch_id = str(batch_id)
    result = _upstream_activate_batch(batch_id)
    if not result['ok']:
        logger.warning('Async batch activation failed for batch=%s: %s', batch_id, result.get('error'))
        return {'batch_id': batch_id, 'batch_activated': False, 'error': result.get('error')}

    state = cache.get(batch_cache_key(batch_id))
    if state:
        state['batch_activated'] = True
        for entry in state.get('hospitals', []):
            if entry.get('status') == 'created':
                entry['status'] = 'created_and_activated'
        _save_state(state)
    return {'batch_id': batch_id, 'batch_activated': True, 'error': None}


@shared_task(name='bulk.delete_batch_async')
def delete_batch_async(batch_id):
    """
    Delete every hospital in a batch via the upstream DELETE endpoint.
    Wipes locally cached batch state on success so the JSON status endpoint
    stops reporting hospitals that no longer exist.
    """
    batch_id = str(batch_id)
    result = _upstream_delete_batch(batch_id)
    if not result['ok']:
        logger.warning('Async batch delete failed for batch=%s: %s', batch_id, result.get('error'))
        return {'batch_id': batch_id, 'deleted': False, 'error': result.get('error')}

    cache.delete(batch_cache_key(batch_id))
    return {'batch_id': batch_id, 'deleted': True, 'error': None}


@shared_task(name='bulk.retry_failed_rows')
def retry_failed_rows(batch_id, rows_with_index):
    """
    Retry just the failed rows of a batch. No activation — operators activate
    explicitly via the batch activate endpoint when they want the batch live.
    rows_with_index: list of {'row': <1-based index>, 'name','address','phone'}.
    """
    state = cache.get(batch_cache_key(batch_id))
    if not state:
        logger.warning('retry_failed_rows: no state for batch=%s', batch_id)
        return None

    state['status'] = 'in_progress'
    state['error'] = None
    started_at = time.monotonic()
    _save_state(state)

    for item in rows_with_index:
        row_index = item['row']
        entry = state['hospitals'][row_index - 1]
        entry['status'] = 'pending'
        entry['error'] = None
        result = create_hospital(item, batch_id)
        if result['ok']:
            data = result.get('data') or {}
            entry['hospital_id'] = data.get('id')
            entry['status'] = 'created'
            entry['error'] = None
            state['failed_hospitals'] = max(0, state['failed_hospitals'] - 1)
        else:
            entry['status'] = 'failed'
            entry['error'] = result.get('error')
        _save_state(state)

    state['processing_time_seconds'] = round(
        state.get('processing_time_seconds', 0) + (time.monotonic() - started_at), 2,
    )
    state['status'] = 'complete'
    state['error'] = None
    _save_state(state)
    return {'batch_id': batch_id}
