import logging
import uuid

from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from bulk.services.hospital_api import (
    activate_batch,
    create_hospital,
    delete_hospital,
    get_hospital,
    list_hospitals,
    list_hospitals_by_batch,
    update_hospital,
)
from utils.pagination_mixin import PaginationMixin

from .forms import HospitalForm

logger = logging.getLogger(__name__)


PAGE_SIZE = 10


def _filter(hospitals, q):
    if not q:
        return hospitals
    q = q.lower()
    return [
        h for h in hospitals
        if q in (h.get('name') or '').lower()
        or q in (h.get('address') or '').lower()
        or q in (h.get('phone') or '').lower()
    ]


class HospitalListView(PaginationMixin, View):
    def get(self, request):
        q = request.GET.get('q', '').strip()
        batch_id = request.GET.get('batch_id', '').strip()
        api_error = None

        if batch_id:
            try:
                uuid.UUID(batch_id)
            except ValueError:
                result = {'ok': True, 'data': []}
                api_error = f'Invalid batch id: {batch_id!r} (expected UUID).'
            else:
                result = list_hospitals_by_batch(batch_id)
        else:
            result = list_hospitals()

        if not result.get('ok') and api_error is None:
            api_error = result.get('error')

        all_hospitals = _filter(result.get('data') or [], q)
        page, meta = self.paginate_queryset(request, all_hospitals, page_size=PAGE_SIZE)
        context = {
            'page_title': 'Hospitals',
            'breadcrumbs': [{'label': 'Hospitals', 'url': None}],
            'hospitals': list(page),
            'pagination': meta,
            'q': q,
            'batch_id': batch_id,
            'api_error': api_error,
        }
        if request.headers.get('HX-Request'):
            return render(request, 'hospital_management/_list_region.html', context)
        return render(request, 'hospital_management/list.html', context)


class HospitalNewFormView(View):
    """Returns a blank inline form row for the create flow."""
    def get(self, request):
        return render(request, 'hospital_management/_form_row.html', {
            'form': HospitalForm(),
            'action_url': reverse('hospital_management:create'),
            'cancel_url': reverse('hospital_management:new_form_cancel'),
        })


class HospitalNewFormCancelView(View):
    """Cancel for the *new* row — just remove it."""
    def get(self, request):
        return HttpResponse('')


class HospitalCreateView(View):
    def post(self, request):
        form = HospitalForm(request.POST)
        if not form.is_valid():
            return render(request, 'hospital_management/_form_row.html', {
                'form': form,
                'action_url': reverse('hospital_management:create'),
                'cancel_url': reverse('hospital_management:new_form_cancel'),
            })
        # Always create with a unique batch_id so the upstream API marks
        # the new hospital as inactive — operators activate explicitly.
        result = create_hospital(form.cleaned_data, batch_id=uuid.uuid4())
        if not result['ok']:
            return render(request, 'hospital_management/_form_row.html', {
                'form': form,
                'action_url': reverse('hospital_management:create'),
                'cancel_url': reverse('hospital_management:new_form_cancel'),
                'api_error': result.get('error'),
            })
        return render(request, 'hospital_management/_row.html', {'hospital': result['data']})


class HospitalActivateView(View):
    """PATCH the upstream batch endpoint to activate the hospital, then refresh the row."""
    def post(self, request, pk):
        h = get_hospital(pk)
        if not h['ok']:
            return HttpResponse(status=404)
        batch_id = (h['data'] or {}).get('creation_batch_id')
        if not batch_id:
            return HttpResponse(
                "<tr><td colspan='8' class='text-danger small'>Cannot activate: hospital has no batch id.</td></tr>",
                status=200,
            )
        result = activate_batch(batch_id)
        if not result['ok']:
            return HttpResponse(
                f"<tr><td colspan='8' class='text-danger small'>Activate failed: {result.get('error')}</td></tr>",
                status=200,
            )
        refreshed = get_hospital(pk)
        return render(request, 'hospital_management/_row.html', {'hospital': refreshed['data']})


class HospitalRowView(View):
    """Single row HTML — used to swap the edit form back to a normal row on cancel."""
    def get(self, request, pk):
        result = get_hospital(pk)
        if not result['ok']:
            return HttpResponse(status=404)
        return render(request, 'hospital_management/_row.html', {'hospital': result['data']})


class HospitalEditFormView(View):
    """Returns the inline edit form for an existing row."""
    def get(self, request, pk):
        result = get_hospital(pk)
        if not result['ok']:
            return HttpResponse(status=404)
        h = result['data']
        form = HospitalForm(initial={
            'name': h.get('name'),
            'address': h.get('address'),
            'phone': h.get('phone') or '',
        })
        return render(request, 'hospital_management/_form_row.html', {
            'form': form,
            'hospital': h,
            'action_url': reverse('hospital_management:update', args=[pk]),
            'cancel_url': reverse('hospital_management:row', args=[pk]),
        })


class HospitalUpdateView(View):
    def post(self, request, pk):
        form = HospitalForm(request.POST)
        if not form.is_valid():
            return render(request, 'hospital_management/_form_row.html', {
                'form': form,
                'hospital': {'id': pk},
                'action_url': reverse('hospital_management:update', args=[pk]),
                'cancel_url': reverse('hospital_management:row', args=[pk]),
            })
        result = update_hospital(pk, form.cleaned_data)
        if not result['ok']:
            return render(request, 'hospital_management/_form_row.html', {
                'form': form,
                'hospital': {'id': pk},
                'action_url': reverse('hospital_management:update', args=[pk]),
                'cancel_url': reverse('hospital_management:row', args=[pk]),
                'api_error': result.get('error'),
            })
        return render(request, 'hospital_management/_row.html', {'hospital': result['data']})


class HospitalDeleteView(View):
    def delete(self, request, pk):
        result = delete_hospital(pk)
        if not result['ok']:
            return HttpResponse(
                f"<tr><td colspan='8' class='text-danger small'>Delete failed: {result.get('error')}</td></tr>",
                status=200,
            )
        return HttpResponse('')


class SearchHospitalsByBatch(View):
    """Returns a blank inline form row for the create flow."""
    def get(self, request):
        return render(request, 'hospital_management/_form_row.html', {
            'form': HospitalForm(),
            'action_url': reverse('hospital_management:create'),
            'cancel_url': reverse('hospital_management:new_form_cancel'),
        })