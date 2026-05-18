from django import forms
from django.core.exceptions import ValidationError

from common.base_forms import BaseForm

from bulk.constant import MAX_UPLOAD_BYTES

from .services.csv_parser import parse_and_validate




class BatchActivateForm(BaseForm):
    batch_id = forms.UUIDField(
        label='Batch ID',
        help_text='UUID of the batch to activate (e.g. 550e8400-e29b-41d4-a716-446655440000).',
    )


class BatchDeleteForm(BaseForm):
    batch_id = forms.UUIDField(
        label='Batch ID',
        help_text='UUID of the batch to delete. Every hospital in this batch will be removed.',
    )


class CSVUploadForm(BaseForm):
    csv = forms.FileField(label='Hospital CSV', help_text='CSV with columns: name, address, phone (optional). Max 20 rows.')

    def clean_csv(self):
        uploaded = self.cleaned_data['csv']
        if uploaded.size > MAX_UPLOAD_BYTES:
            raise ValidationError(f'File too large ({uploaded.size} bytes). Max is {MAX_UPLOAD_BYTES} bytes.')

        name = (uploaded.name or '').lower()
        if not name.endswith('.csv'):
            raise ValidationError('File must have a .csv extension.')

        rows = parse_and_validate(uploaded)
        self.cleaned_data['rows'] = rows
        return uploaded
