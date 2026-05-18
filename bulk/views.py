import uuid

from django.contrib import messages
from django.shortcuts import render
from django.urls import reverse_lazy
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from common.base_views import BaseFormView

from .forms import BatchActivateForm, BatchDeleteForm, CSVUploadForm
from .tasks import activate_batch_async, delete_batch_async, process_batch
from bulk.constant import BATCH_GROUP_NAME


class BulkUploadView(BaseFormView):
    form_class = CSVUploadForm
    template_name = 'bulk/upload.html'
    page_title = 'Hospital Bulk Upload'
    success_url = reverse_lazy('bulk:upload')

    def _get_breadcrumbs(self):
        return [{'label': 'Bulk Upload', 'url': None}]

    def form_valid(self, form):
        batch_id = uuid.uuid4()
        rows = form.cleaned_data['rows']
        process_batch.delay(str(batch_id), rows)
        context = {
            'batch_id': str(batch_id),
            'total': len(rows),
            'processed': 0,
            'failed': 0,
            'status': 'queued',
            'batch_activated': False,
        }
        return render(self.request, 'bulk/_progress.html', context)

    def form_invalid(self, form):
        return render(self.request, 'bulk/_form.html', {'form': form})
    
    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)
        context['batch_group_name'] = BATCH_GROUP_NAME

        return context


class BatchActivateView(BaseFormView):
    form_class = BatchActivateForm
    template_name = 'bulk/activate.html'
    page_title = 'Bulk Activate Batch'
    success_url = reverse_lazy('hospital_management:list')

    def _get_breadcrumbs(self):
        return [{'label': 'Bulk Activate', 'url': None}]

    def form_valid(self, form):
        batch_id = str(form.cleaned_data['batch_id'])
        activate_batch_async.delay(batch_id)
        messages.success(
            self.request,
            f'Activation queued for batch {batch_id}. Hospitals will turn active once the worker finishes.',
        )
        return super().form_valid(form)


class BatchDeleteView(BaseFormView):
    form_class = BatchDeleteForm
    template_name = 'bulk/delete.html'
    page_title = 'Bulk Delete Batch'
    success_url = reverse_lazy('hospital_management:list')

    def _get_breadcrumbs(self):
        return [{'label': 'Bulk Delete', 'url': None}]

    def form_valid(self, form):
        batch_id = str(form.cleaned_data['batch_id'])
        delete_batch_async.delay(batch_id)
        messages.warning(
            self.request,
            f'Delete queued for batch {batch_id}. Every hospital in this batch will be removed once the worker finishes.',
        )
        return super().form_valid(form)

