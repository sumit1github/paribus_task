"""
Tests for the bulk hospital-processing JSON API and the CSV parser.

Run with: python manage.py test bulk
"""
from io import BytesIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .services.csv_parser import parse_and_validate
from .tasks import (
    activate_batch_async,
    batch_cache_key,
    delete_batch_async,
    make_initial_state,
    process_batch,
)


def _csv(content):
    return SimpleUploadedFile('hospitals.csv', content.encode('utf-8'), content_type='text/csv')


SAMPLE_CSV = (
    'name,address,phone\n'
    'City Hospital,123 NY St,1234567890\n'
    'General Hospital,456 LA Blvd,\n'
)


class CSVParserTests(TestCase):
    def test_parses_valid_csv(self):
        rows = parse_and_validate(_csv(SAMPLE_CSV))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {'name': 'City Hospital', 'address': '123 NY St', 'phone': '1234567890'})
        self.assertEqual(rows[1]['phone'], '')

    def test_missing_required_column(self):
        with self.assertRaises(ValidationError) as ctx:
            parse_and_validate(_csv('name,phone\nCity,1234\n'))
        self.assertIn('address', str(ctx.exception))

    def test_empty_required_field(self):
        with self.assertRaises(ValidationError):
            parse_and_validate(_csv('name,address,phone\n,123 St,123\n'))

    def test_enforces_max_rows(self):
        rows = '\n'.join(f'H{i},addr,123' for i in range(21))
        with self.assertRaises(ValidationError) as ctx:
            parse_and_validate(_csv(f'name,address,phone\n{rows}\n'))
        self.assertIn('maximum is 20', str(ctx.exception))

    def test_empty_csv_rejected(self):
        with self.assertRaises(ValidationError):
            parse_and_validate(_csv('name,address,phone\n'))


class BulkAPITests(TestCase):
    def setUp(self):
        cache.clear()

    def _post_csv(self, url, content=SAMPLE_CSV, field='file'):
        return self.client.post(url, {field: _csv(content)})

    @patch('bulk.api_views.process_batch.delay')
    def test_upload_returns_202_with_batch_id(self, mock_delay):
        response = self._post_csv(reverse('bulk_api:upload'))
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertIn('batch_id', body)
        self.assertEqual(body['total_hospitals'], 2)
        self.assertEqual(body['status'], 'queued')
        mock_delay.assert_called_once()

    @patch('bulk.api_views.process_batch.delay')
    def test_upload_seeds_state_for_immediate_get(self, _mock):
        response = self._post_csv(reverse('bulk_api:upload'))
        batch_id = response.json()['batch_id']
        status = self.client.get(reverse('bulk_api:status', args=[batch_id]))
        self.assertEqual(status.status_code, 200)
        body = status.json()
        self.assertEqual(body['total_hospitals'], 2)
        self.assertEqual(body['status'], 'queued')
        self.assertEqual(len(body['hospitals']), 2)
        # Internal fields stripped.
        self.assertNotIn('_rows_by_index', body)

    def test_upload_missing_file_returns_400(self):
        response = self.client.post(reverse('bulk_api:upload'), {})
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_upload_rejects_non_csv_extension(self):
        bad = SimpleUploadedFile('hospitals.txt', SAMPLE_CSV.encode(), content_type='text/csv')
        response = self.client.post(reverse('bulk_api:upload'), {'file': bad})
        self.assertEqual(response.status_code, 400)

    def test_upload_validation_errors_returned(self):
        response = self._post_csv(reverse('bulk_api:upload'), 'name,phone\nCity,1234\n')
        self.assertEqual(response.status_code, 400)
        self.assertIn('details', response.json())

    def test_status_404_for_unknown_batch(self):
        response = self.client.get(reverse('bulk_api:status', args=['00000000-0000-0000-0000-000000000000']))
        self.assertEqual(response.status_code, 404)

    def test_validate_endpoint_happy_path(self):
        response = self._post_csv(reverse('bulk_api:validate'))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['valid'])
        self.assertEqual(body['total_hospitals'], 2)
        self.assertEqual(len(body['preview']), 2)

    def test_validate_endpoint_returns_errors(self):
        response = self._post_csv(reverse('bulk_api:validate'), 'name,phone\nCity,1234\n')
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body['valid'])
        self.assertIn('errors', body)


class BatchEndpointTests(TestCase):
    """Thin proxies to the external API — exercise the routing + dispatch."""

    BATCH_ID = '44444444-4444-4444-4444-444444444444'

    def setUp(self):
        cache.clear()

    @patch('bulk.api_views.list_hospitals_by_batch')
    def test_get_batch_hospitals_returns_upstream_list(self, mock_list):
        mock_list.return_value = {
            'ok': True, 'status': 200, 'error': None,
            'data': [{'id': 1, 'name': 'A'}, {'id': 2, 'name': 'B'}],
        }
        response = self.client.get(reverse('batch_api:hospitals', args=[self.BATCH_ID]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{'id': 1, 'name': 'A'}, {'id': 2, 'name': 'B'}])
        mock_list.assert_called_once()

    @patch('bulk.api_views.list_hospitals_by_batch')
    def test_get_batch_hospitals_propagates_upstream_error(self, mock_list):
        mock_list.return_value = {'ok': False, 'status': 404, 'error': 'Not found', 'data': None}
        response = self.client.get(reverse('batch_api:hospitals', args=[self.BATCH_ID]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error'], 'Not found')

    @patch('bulk.api_views.delete_hospitals_by_batch')
    def test_delete_batch_clears_local_state(self, mock_delete):
        mock_delete.return_value = {'ok': True, 'status': 200, 'error': None, 'data': None}
        cache.set(batch_cache_key(self.BATCH_ID), {'stub': True}, timeout=60)

        response = self.client.delete(reverse('batch_api:hospitals', args=[self.BATCH_ID]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['deleted'])
        self.assertIsNone(cache.get(batch_cache_key(self.BATCH_ID)))
        mock_delete.assert_called_once()

    @patch('bulk.api_views.activate_batch')
    def test_patch_activate_flips_local_state(self, mock_activate):
        mock_activate.return_value = {'ok': True, 'status': 200, 'error': None}
        cache.set(
            batch_cache_key(self.BATCH_ID),
            {
                'batch_id': self.BATCH_ID,
                'batch_activated': False,
                'hospitals': [
                    {'row': 1, 'status': 'created'},
                    {'row': 2, 'status': 'failed'},
                ],
            },
            timeout=60,
        )

        response = self.client.patch(reverse('batch_api:activate', args=[self.BATCH_ID]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['activated'])
        state = cache.get(batch_cache_key(self.BATCH_ID))
        self.assertTrue(state['batch_activated'])
        # 'created' is promoted, 'failed' is left alone.
        self.assertEqual([h['status'] for h in state['hospitals']], ['created_and_activated', 'failed'])

    @patch('bulk.api_views.activate_batch')
    def test_patch_activate_works_without_local_state(self, mock_activate):
        mock_activate.return_value = {'ok': True, 'status': 200, 'error': None}
        response = self.client.patch(reverse('batch_api:activate', args=[self.BATCH_ID]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['activated'])


class ProcessBatchTaskTests(TestCase):
    """Run the Celery task synchronously with the external API mocked."""

    def setUp(self):
        cache.clear()

    @patch('bulk.tasks.send_progress')  # don't try to push to a real channel layer
    @patch('bulk.tasks.create_hospital')
    def test_happy_path_records_created_rows(self, mock_create, _mock_progress):
        mock_create.side_effect = [
            {'ok': True, 'status': 201, 'error': None, 'data': {'id': 1}},
            {'ok': True, 'status': 201, 'error': None, 'data': {'id': 2}},
        ]
        batch_id = '11111111-1111-1111-1111-111111111111'
        rows = [
            {'name': 'A', 'address': 'addr1', 'phone': '111'},
            {'name': 'B', 'address': 'addr2', 'phone': '222'},
        ]
        cache.set(batch_cache_key(batch_id), make_initial_state(batch_id, rows), timeout=60)

        process_batch(batch_id, rows)

        state = cache.get(batch_cache_key(batch_id))
        self.assertEqual(state['status'], 'complete')
        self.assertFalse(state['batch_activated'])  # never auto-activates anymore
        self.assertEqual(state['processed_hospitals'], 2)
        self.assertEqual(state['failed_hospitals'], 0)
        self.assertEqual([h['status'] for h in state['hospitals']], ['created', 'created'])
        self.assertEqual([h['hospital_id'] for h in state['hospitals']], [1, 2])
        self.assertGreaterEqual(state['processing_time_seconds'], 0)

    @patch('bulk.tasks.send_progress')
    @patch('bulk.tasks.create_hospital')
    def test_partial_failure_records_per_row_errors(self, mock_create, _mock_progress):
        mock_create.side_effect = [
            {'ok': True, 'status': 201, 'error': None, 'data': {'id': 10}},
            {'ok': False, 'status': 422, 'error': 'HTTP 422: bad name', 'data': None},
        ]
        batch_id = '22222222-2222-2222-2222-222222222222'
        rows = [
            {'name': 'A', 'address': 'addr1', 'phone': ''},
            {'name': 'B', 'address': 'addr2', 'phone': ''},
        ]
        cache.set(batch_cache_key(batch_id), make_initial_state(batch_id, rows), timeout=60)

        process_batch(batch_id, rows)

        state = cache.get(batch_cache_key(batch_id))
        self.assertEqual(state['failed_hospitals'], 1)
        self.assertEqual(state['processed_hospitals'], 2)
        self.assertFalse(state['batch_activated'])
        self.assertEqual(state['hospitals'][0]['status'], 'created')
        self.assertEqual(state['hospitals'][1]['status'], 'failed')
        self.assertIn('422', state['hospitals'][1]['error'])

    @patch('bulk.tasks._upstream_activate_batch')
    def test_activate_batch_async_flips_local_state(self, mock_activate):
        mock_activate.return_value = {'ok': True, 'status': 200, 'error': None}
        batch_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        cache.set(
            batch_cache_key(batch_id),
            {
                'batch_id': batch_id,
                'batch_activated': False,
                'hospitals': [
                    {'row': 1, 'status': 'created'},
                    {'row': 2, 'status': 'failed'},
                ],
            },
            timeout=60,
        )

        result = activate_batch_async(batch_id)

        self.assertTrue(result['batch_activated'])
        state = cache.get(batch_cache_key(batch_id))
        self.assertTrue(state['batch_activated'])
        self.assertEqual([h['status'] for h in state['hospitals']], ['created_and_activated', 'failed'])
        mock_activate.assert_called_once_with(batch_id)

    @patch('bulk.tasks._upstream_activate_batch')
    def test_activate_batch_async_handles_upstream_failure(self, mock_activate):
        mock_activate.return_value = {'ok': False, 'status': 404, 'error': 'Not found', 'data': None}
        batch_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'

        result = activate_batch_async(batch_id)

        self.assertFalse(result['batch_activated'])
        self.assertEqual(result['error'], 'Not found')

    @patch('bulk.tasks._upstream_delete_batch')
    def test_delete_batch_async_clears_local_state(self, mock_delete):
        mock_delete.return_value = {'ok': True, 'status': 200, 'error': None, 'data': None}
        batch_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
        cache.set(batch_cache_key(batch_id), {'stub': True}, timeout=60)

        result = delete_batch_async(batch_id)

        self.assertTrue(result['deleted'])
        self.assertIsNone(cache.get(batch_cache_key(batch_id)))
        mock_delete.assert_called_once_with(batch_id)

    @patch('bulk.tasks._upstream_delete_batch')
    def test_delete_batch_async_handles_upstream_failure(self, mock_delete):
        mock_delete.return_value = {'ok': False, 'status': 404, 'error': 'Not found', 'data': None}
        batch_id = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
        cache.set(batch_cache_key(batch_id), {'stub': True}, timeout=60)

        result = delete_batch_async(batch_id)

        self.assertFalse(result['deleted'])
        # On failure the local state is preserved so the operator can retry.
        self.assertIsNotNone(cache.get(batch_cache_key(batch_id)))

    @patch('bulk.tasks.send_progress')
    @patch('bulk.tasks.create_hospital', return_value={'ok': False, 'status': 500, 'error': 'boom', 'data': None})
    def test_all_failed_completes_without_activation(self, _mock_create, _mock_progress):
        batch_id = '33333333-3333-3333-3333-333333333333'
        rows = [{'name': 'A', 'address': 'addr', 'phone': ''}]
        cache.set(batch_cache_key(batch_id), make_initial_state(batch_id, rows), timeout=60)

        process_batch(batch_id, rows)

        state = cache.get(batch_cache_key(batch_id))
        self.assertEqual(state['status'], 'complete')
        self.assertFalse(state['batch_activated'])
        self.assertEqual(state['failed_hospitals'], 1)
        self.assertEqual(state['hospitals'][0]['status'], 'failed')
