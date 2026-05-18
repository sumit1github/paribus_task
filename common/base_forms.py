from collections import OrderedDict
from functools import reduce
from itertools import chain
from operator import add
from collections.abc import Iterable
from django import forms
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.forms import BaseFormSet
from django.forms.utils import ErrorList
from django.utils.safestring import mark_safe


class InlineRadioSelect(forms.RadioSelect):
    """Custom RadioSelect widget that renders options inline (side by side)"""
    template_name = 'common/widgets/inline_radio.html'

    def get_context(self, name, value, attrs):
        if value is None:
            value = ""
        elif isinstance(value, bool):
            value = str(value)
        context = super().get_context(name, value, attrs)
        context["widget"]["option_groups"] = self.optgroups(name, value, attrs)
        return context


class ModernCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """Custom CheckboxSelectMultiple widget with modern card-style checkboxes"""
    template_name = 'common/widgets/checkbox_select.html'

    def get_context(self, name, value, attrs):
        if value is None:
            value = []
        elif isinstance(value, bool):
            value = [str(value)]
        elif isinstance(value, str):
            value = [value]
        elif not isinstance(value, Iterable):
            value = [value]
        context = super().get_context(name, value, attrs)
        context["widget"]["option_groups"] = self.optgroups(name, value, attrs)
        return context


class FormStylingMixin:
    """
    Applies Bootstrap styling and consistent widget conversions to any
    Django form (ModelForm or plain Form). Designed to be mixed-in BEFORE
    forms.ModelForm / forms.Form in the MRO so its __init__ runs on subclasses.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.convert_boolean_fields()
        self.convert_multiselect_fields()
        self.add_form_classes()

    def convert_boolean_fields(self):
        """
        Convert all boolean fields to inline radio buttons with Yes/No options.
        """
        for field_name, field in self.fields.items():
            # Check if the field is a BooleanField (checkbox by default)
            if isinstance(field, forms.BooleanField) or isinstance(field.widget, forms.CheckboxInput):
                # Convert to TypedChoiceField with InlineRadioSelect widget
                self.fields[field_name] = forms.TypedChoiceField(
                    coerce=lambda x: x == 'True',
                    choices=[(True, 'Yes'), (False, 'No')],
                    widget=InlineRadioSelect(),
                    required=field.required,
                    label=field.label,
                    help_text=field.help_text,
                    initial=field.initial,
                )

    def convert_multiselect_fields(self):
        """
        Convert all MultipleChoiceField and ModelMultipleChoiceField to modern checkbox style.
        """
        for field_name, field in self.fields.items():
            # Check if the field is a multiple choice field with SelectMultiple widget
            if isinstance(field, (forms.MultipleChoiceField, forms.ModelMultipleChoiceField)):
                if isinstance(field.widget, forms.SelectMultiple) and not isinstance(field.widget, forms.CheckboxSelectMultiple):
                    # Replace the widget with ModernCheckboxSelectMultiple
                    field.widget = ModernCheckboxSelectMultiple(choices=field.choices)

    def add_form_classes(self):
        """
        Add Bootstrap and field-specific classes to all form fields.
        """
        for field_name, field in self.fields.items():
            # Base Bootstrap classes
            base_classes = 'form-control'
            
            # Convert DateField and DateTimeField to proper widgets if not already set
            if isinstance(field, forms.DateField) and not isinstance(field.widget, forms.DateInput):
                field.widget = forms.DateInput(attrs={'type': 'date'})
            elif isinstance(field, forms.DateTimeField) and not isinstance(field.widget, forms.DateTimeInput):
                field.widget = forms.DateTimeInput(attrs={'type': 'datetime-local'})
            
            # Add specific classes based on field type
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, forms.RadioSelect):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = f'{base_classes} form-select'
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs['class'] = f'{base_classes} textarea-field'
            elif isinstance(field.widget, forms.DateTimeInput):
                field.widget.attrs['class'] = f'{base_classes} datetime-field'
                field.widget.attrs['type'] = 'datetime-local'
            elif isinstance(field.widget, forms.DateInput):
                field.widget.attrs['class'] = f'{base_classes} date-field'
                field.widget.attrs['type'] = 'date'
            elif isinstance(field.widget, forms.TimeInput):
                field.widget.attrs['class'] = f'{base_classes} time-field'
                field.widget.attrs['type'] = 'time'
            elif isinstance(field.widget, forms.EmailInput):
                field.widget.attrs['class'] = f'{base_classes} email-field'
            elif isinstance(field.widget, forms.URLInput):
                field.widget.attrs['class'] = f'{base_classes} url-field'
            elif isinstance(field.widget, forms.NumberInput):
                field.widget.attrs['class'] = f'{base_classes} number-field'
            elif isinstance(field.widget, forms.PasswordInput):
                field.widget.attrs['class'] = f'{base_classes} password-field'
            else:
                field.widget.attrs['class'] = f'{base_classes} text-field'
            
            # Add placeholder
            if not field.widget.attrs.get('placeholder'):
                field.widget.attrs['placeholder'] = f'Enter {field_name.replace("_", " ")}'


class BaseModelForm(FormStylingMixin, forms.ModelForm):
    """Bootstrap-styled ModelForm. Subclass for model-bound forms."""
    pass


class BaseForm(FormStylingMixin, forms.Form):
    """Bootstrap-styled non-model Form. Subclass for plain forms."""
    pass


class MultiForm:
    """
    A container that allows you to treat multiple forms as one form.  This is
    great for using more than one form on a page that share the same submit
    button.  MultiForm imitates the Form API so that it is invisible to anybody
    else that you are using a MultiForm.
    """
    form_classes = {}

    def __init__(self, data=None, files=None, request=None, *args, **kwargs):
        self.data, self.files = data, files
        kwargs.update(data=data, files=files)
        self.initials = kwargs.pop("initial", None) or {}
        self.requests = kwargs.pop("requests", None) or {}
        self.forms = OrderedDict()
        self.crossform_errors = []
        for key, form_class in self.form_classes.items():
            fargs, fkwargs = self.get_form_args_kwargs(key, args, kwargs)
            try:
                fkwargs["queryset"] = fkwargs.get("initial").pop("queryset")
            except (AttributeError, KeyError):
                pass
            self.forms[key] = form_class(*fargs, **fkwargs)

    def get_form_args_kwargs(self, key, args, kwargs):
        fkwargs = kwargs.copy()
        prefix = kwargs.get("prefix")
        prefix = key if prefix is None else f"{key}__{prefix}"
        fkwargs.update(initial=self.initials.get(key), prefix=prefix)
        if self.requests and self.requests.get(key):
            fkwargs.update(request=self.requests.get(key))
        return args, fkwargs

    def __getitem__(self, key):
        return self.forms[key]

    @property
    def items(self):
        return self.forms.items()

    @property
    def errors(self):
        errors = {}
        for form_name, form in self.forms.items():
            if not isinstance(form, BaseFormSet):
                for field_name, field_errors in form.errors.items():
                    prefixed_field_name = form.add_prefix(field_name)
                    if prefixed_field_name not in errors:
                        errors[prefixed_field_name] = field_errors
                    else:
                        errors[prefixed_field_name].extend(field_errors)
            else:
                formset_non_form_errors = {}
                for index, subform in enumerate(form.forms):
                    if subform.errors:
                        row_errors = {}
                        for field_name, field_errors in subform.errors.items():
                            row_errors[field_name] = field_errors[0]
                        if row_errors:
                            if form_name not in formset_non_form_errors:
                                formset_non_form_errors[form_name] = []
                            formset_non_form_errors[form_name].append({"row_index": index, "errors": row_errors})
                if formset_non_form_errors:
                    if "non_form_errors" not in errors:
                        errors["non_form_errors"] = formset_non_form_errors
                    else:
                        errors["non_form_errors"].update(formset_non_form_errors)
        if self.crossform_errors:
            if NON_FIELD_ERRORS not in errors:
                errors[NON_FIELD_ERRORS] = self.crossform_errors
            else:
                errors[NON_FIELD_ERRORS].extend(self.crossform_errors)
        return errors

    @property
    def fields(self):
        fields = []
        for form_name in self.forms:
            form = self.forms[form_name]
            for field_name in form.fields:
                fields += [form.add_prefix(field_name)]
        return fields

    def __iter__(self):
        return chain.from_iterable(self.forms.values())

    @property
    def is_bound(self):
        return any(form.is_bound for form in self.forms.values())

    def clean(self):
        return self.cleaned_data

    def add_crossform_error(self, e):
        self.crossform_errors.append(e)

    def is_valid(self):
        try:
            self.cleaned_data = self.clean()
        except ValidationError as e:
            self.add_crossform_error(e)
        forms_valid = all(form.is_valid() for form in self.forms.values())
        return forms_valid and not self.crossform_errors

    def non_field_errors(self):
        form_errors = (form.non_field_errors() for form in self.forms.values() if hasattr(form, "non_field_errors"))
        return ErrorList(chain(self.crossform_errors, *form_errors))

    @property
    def media(self):
        return reduce(add, (form.media for form in self.forms.values()))

    def hidden_fields(self):
        return [field for field in self if field.is_hidden]

    def visible_fields(self):
        return [field for field in self if not field.is_hidden]

    @property
    def cleaned_data(self):
        return OrderedDict((key, form.cleaned_data) for key, form in self.forms.items() if form.is_valid())

    @cleaned_data.setter
    def cleaned_data(self, data):
        for key, value in data.items():
            child_form = self[key]
            if isinstance(child_form, BaseFormSet):
                for formlet, formlet_data in zip(child_form.forms, value, strict=False):
                    formlet.cleaned_data = formlet_data
            else:
                child_form.cleaned_data = value


class MultiModelForm(MultiForm):

    """
    MultiModelForm adds ModelForm support on top of MultiForm.  That simply
    means that it includes support for the instance parameter in initialization
    and adds a save method.
    """
    def __init__(self, *args, request=None,**kwargs):
        self.instances = kwargs.pop("instance", None)
        super().__init__(*args, **kwargs)

    def get_form_args_kwargs(self, key, args, kwargs):
        fargs, fkwargs = super().get_form_args_kwargs(key, args, kwargs)
        if self.instances and isinstance(self.instances, dict):
            fkwargs["instance"] = self.instances.get(key)
        else:
            fkwargs["instance"] = self.instances
        return fargs, fkwargs

    def save(self, commit=True):
        objects = OrderedDict((key, form.save(commit)) for key, form in self.forms.items())
        if any(hasattr(form, "save_m2m") for form in self.forms.values()):
            def save_m2m():
                for form in self.forms.values():
                    if hasattr(form, "save_m2m"):
                        form.save_m2m()
            self.save_m2m = save_m2m
        return objects
    
 
class ReadOnlyHTMLWidget(forms.Widget):
    """
    A custom widget that displays readonly data as HTML instead of an input box.
    """
    def __init__(self, display_value=None, html_template=None, attrs=None):
        self.display_value = display_value
        self.html_template = html_template or '<div class="readonly-field">{value}</div>'
        super().__init__(attrs)

    def render(self, name, value, attrs=None, renderer=None):
        final_value = self.display_value or value or ''
        
        # Try to convert to numeric if the template expects numeric formatting
        if '{value:' in self.html_template and final_value:
            try:
                if isinstance(final_value, str):
                    final_value = float(final_value)
            except (ValueError, TypeError):
                pass  # Keep the original value if conversion fails
        
        try:
            # Try to format with the template
            html_output = self.html_template.format(value=final_value)
        except (ValueError, KeyError, IndexError):
            # If formatting still fails, convert to string and try again
            try:
                html_output = self.html_template.format(value=str(final_value))
            except (ValueError, KeyError, IndexError):
                # Last resort: strip the format specifier and just output the value
                # Replace {value:something} with just the string value
                import re
                simple_template = re.sub(r'\{value[^}]*\}', str(final_value), self.html_template)
                html_output = simple_template
        
        return mark_safe(html_output)


class ReadOnlyField(forms.CharField):
    """
    A custom field that uses ReadOnlyHTMLWidget to display data as readonly HTML.

    from common.forms import ReadOnlyField
    ReadOnlyField(
        label='Student Name',
        html_template='<div class="alert alert-info"><strong>{value}</strong></div>'
    )

    """
    def __init__(self, *args, label=None, display_value=None, html_template=None, **kwargs):
        self.display_value = display_value
        self.html_template = html_template
        kwargs['required'] = False
        kwargs['widget'] = ReadOnlyHTMLWidget(
            display_value=display_value,
            html_template=html_template
        )
        super().__init__(*args, label=label, **kwargs)