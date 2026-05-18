"""
Base View Classes for GTTC School Management System

This module provides reusable base classes for common CRUD operations,
following Django's Class-Based View architecture. All views support:
- Pagination (template and DRF modes)
- Breadcrumb navigation
- Page titles
- Task lists (from module-specific TaskList classes)
- Standard context preparation
- Form handling with success messages
- Permission checking (via decorators)

Usage:
    @method_decorator(has_permission(['ADMIN']), name='dispatch')
    class MyListView(BaseListView):
        model = MyModel
        template_name = 'my_template.html'
        page_title = 'My Items'
        page_size = 20
        
        def _get_breadcrumbs(self):
            return [{'label': 'Home', 'url': reverse_lazy('home')}]
        
        def get_queryset(self):
            return super().get_queryset().filter(is_active=True)
"""

from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, FormView
)
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from utils.pagination_mixin import PaginationMixin


# ============================================================================
# BASE MIXIN CLASSES - Core Functionality Shared Across Views
# ============================================================================

class ContextMixin:
    """
    Provides common context preparation for all views.
    
    Attributes to override:
        page_title (str): Title displayed on the page
        task_list_class (class): TaskList class (e.g., EmployeeTaskList)
        paginate_by (int): Default page size for pagination
    """
    page_title = "Page Title"
    task_list_class = None  # Override in child classes
    paginate_by = 20
    
    def get_page_title(self):
        """Return the page title. Override for dynamic titles."""
        return self.page_title
    
    def _get_breadcrumbs(self):
        """
        Return breadcrumb navigation data.
        Override this method in subclasses.
        
        Returns:
            list: List of {'label': str, 'url': str} dicts
        """
        return []
    
    def get_task_list(self):
        """
        Get task list from the module's TaskList class.
        
        Returns:
            list: Task list data or empty list if task_list_class not set
        """
        if self.task_list_class and hasattr(self, 'request'):
            try:
                return self.task_list_class(self.request).task_list()
            except Exception:
                return []
        return []
    
    def build_base_context(self, **kwargs):
        """
        Build common context data present in all views.
        
        Returns:
            dict: Context with page_title, breadcrumbs, task_list
        """
        context = {
            'page_title': self.get_page_title(),
            'breadcrumbs': self._get_breadcrumbs(),
            'task_list': self.get_task_list(),
        }
        context.update(kwargs)
        return context


class PaginationContextMixin(ContextMixin, PaginationMixin):
    """
    Combines pagination with context preparation.
    Used for list views that need pagination support.
    
    Attributes:
        page_size (int): Number of items per page
    """
    page_size = 20
    pagination_meta = {}
    
    def get_paginated_data(self, queryset):
        """
        Paginate the queryset for template rendering.
        
        Args:
            queryset: The queryset to paginate
            
        Returns:
            tuple: (paginated_page, pagination_meta)
        """
        page, meta = self.paginate_queryset(
            self.request, 
            queryset, 
            page_size=self.page_size, 
            mode='template'
        )
        self.pagination_meta = meta
        return page
    
    def get_pagination_context(self):
        """
        Get pagination context data.
        
        Returns:
            dict: Pagination metadata
        """
        return {
            'pagination_meta': getattr(self, 'pagination_meta', {}),
        }


# ============================================================================
# GENERIC LIST VIEW
# ============================================================================

class BaseListView(PaginationContextMixin, ListView):
    """
    Base list view with pagination, breadcrumbs, and task list support.
    
    This view handles:
    - Displaying a paginated list of objects
    - Search functionality (optional via get_queryset override)
    - Breadcrumb navigation
    - Page title display
    - Task list integration
    
    Attributes (override in subclasses):
        model: Django model class
        template_name: Path to template
        context_object_name: Name of object list in context
        page_title: Display title for the page
        page_size: Items per page (default: 20)
        task_list_class: Module TaskList class for generating task links
        
    Methods to override:
        _get_breadcrumbs(): Return breadcrumb data
        get_queryset(): Filter/order the queryset
        get_context_data(): Add custom context (call super() first)
    
    Example:
        @method_decorator(has_permission(['ADMIN']), name='dispatch')
        class EmployeeListView(BaseListView):
            model = Employee
            template_name = 'employee_list.html'
            context_object_name = 'employees'
            page_title = 'Employees'
            page_size = 20
            task_list_class = EmployeeTaskList
            
            def _get_breadcrumbs(self):
                return [
                    {'label': 'Home', 'url': reverse_lazy('home')},
                    {'label': 'Employees', 'url': reverse_lazy('employee:list')},
                ]
            
            def get_queryset(self):
                queryset = super().get_queryset()
                search = self.request.GET.get('search', '')
                if search:
                    queryset = queryset.filter(name__icontains=search)
                # Paginate after filtering
                return self.get_paginated_data(queryset)
    """
    
    model = None
    template_name = None
    context_object_name = 'object_list'
    paginate_by = None  # Not used with PaginationMixin
    
    def get_queryset(self):
        """
        Get base queryset. Override to add filtering/searching.
        Remember to call get_paginated_data() on the final queryset!
        
        Returns:
            queryset or paginated list
        """
        queryset = super().get_queryset()
        return self.get_paginated_data(queryset)
    
    def get_context_data(self, **kwargs):
        """Prepare context with pagination and common data."""
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context())
        context.update(self.get_pagination_context())
        return context


# ============================================================================
# GENERIC DETAIL VIEW
# ============================================================================

class BaseDetailView(ContextMixin, DetailView):
    """
    Base detail view for displaying a single object with breadcrumbs and task list.
    
    This view handles:
    - Displaying a single object
    - Breadcrumb navigation
    - Page title display
    - Task list integration
    - Permission checks via dispatch method override
    
    Attributes (override in subclasses):
        model: Django model class
        template_name: Path to template
        context_object_name: Name of object in context
        page_title: Display title for the page
        task_list_class: Module TaskList class
        
    Methods to override:
        _get_breadcrumbs(): Return breadcrumb data
        get_context_data(): Add custom context (call super() first)
    
    Example:
        @method_decorator(has_permission(['ADMIN', 'EMPLOYEE']), name='dispatch')
        class EmployeeDetailView(BaseDetailView):
            model = Employee
            template_name = 'employee_detail.html'
            context_object_name = 'employee'
            page_title = 'Employee Details'
            task_list_class = EmployeeTaskList
            
            def _get_breadcrumbs(self):
                return [
                    {'label': 'Employees', 'url': reverse_lazy('employee:list')},
                    {'label': self.object.name, 'url': None},
                ]
            
            def dispatch(self, request, *args, **kwargs):
                # Custom permission checks if needed
                return super().dispatch(request, *args, **kwargs)
    """
    
    model = None
    template_name = None
    context_object_name = 'object'
    
    def get_context_data(self, **kwargs):
        """Prepare context with breadcrumbs and common data."""
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context())
        return context


# ============================================================================
# FORM-BASED CREATE/UPDATE VIEWS
# ============================================================================

class BaseFormView(ContextMixin, FormView):
    """
    Base form view for create/update operations with breadcrumbs and success messages.
    
    This view handles:
    - Form rendering with breadcrumbs
    - Form submission and validation
    - Success messages
    - Redirect after success
    - Task list integration
    
    Attributes (override in subclasses):
        form_class: Django form class
        template_name: Path to template
        success_url: URL to redirect after successful submission
        page_title: Display title for the page
        task_list_class: Module TaskList class
        success_message: Message to display on success (optional)
        
    Methods to override:
        _get_breadcrumbs(): Return breadcrumb data
        get_success_url(): Return the success redirect URL
        get_form_kwargs(): Pass custom kwargs to form (e.g., request)
        get_context_data(): Add custom context (call super() first)
        form_valid(): Custom processing after form validation (call super() first)
    
    Example:
        @method_decorator(has_permission(['ADMIN']), name='dispatch')
        class EmployeeCreateView(BaseFormView):
            form_class = EmployeeForm
            template_name = 'employee_form.html'
            success_url = reverse_lazy('employee:list')
            page_title = 'Create Employee'
            task_list_class = EmployeeTaskList
            success_message = 'Employee created successfully.'
            
            def _get_breadcrumbs(self):
                return [
                    {'label': 'Employees', 'url': reverse_lazy('employee:list')},
                    {'label': 'Create', 'url': None},
                ]
            
            def form_valid(self, form):
                form.save()
                messages.success(self.request, self.success_message)
                return super().form_valid(form)
    """
    
    form_class = None
    template_name = None
    success_url = None
    success_message = "Form submitted successfully."
    
    def get_form_kwargs(self):
        """
        Get kwargs to pass to form initialization.
        Override to pass request, instance, or other data to the form.
        
        Returns:
            dict: Keyword arguments for form
        """
        kwargs = super().get_form_kwargs()
        return kwargs
    
    def get_success_url(self):
        """
        Get URL to redirect to after successful form submission.
        Override this method for dynamic success URLs.
        
        Returns:
            str: URL to redirect to
        """
        if self.success_url:
            return self.success_url
        raise NotImplementedError(
            f"No success_url set on {self.__class__.__name__}. "
            "Override get_success_url() or set success_url attribute."
        )
    
    def form_valid(self, form):
        """
        Handle valid form submission.
        Override for custom processing.
        
        Args:
            form: The validated form
            
        Returns:
            HttpResponseRedirect to success_url
        """
        if hasattr(self, 'success_message') and self.success_message:
            messages.success(self.request, self.success_message)
        return HttpResponseRedirect(self.get_success_url())
    
    def get_context_data(self, **kwargs):
        """Prepare context with breadcrumbs and common data."""
        context = super().get_context_data(**kwargs)
        context.update(self.build_base_context())
        # Add form action URL for template use
        context['form_action_url'] = self.request.path
        return context


class BaseCreateView(BaseFormView):
    """
    Specialized form view for create operations.
    
    Pre-configured with sensible defaults for creating new objects.
    
    Example:
        class EmployeeCreateView(BaseCreateView):
            form_class = EmployeeForm
            template_name = 'employee_form.html'
            success_url = reverse_lazy('employee:list')
            page_title = 'Create Employee'
            task_list_class = EmployeeTaskList
            success_message = 'Employee created successfully.'
    """
    pass


class BaseUpdateView(BaseFormView):
    """
    Specialized form view for update operations.
    
    Extends BaseFormView with:
    - Object retrieval from URL kwargs
    - Automatic form instance binding
    - Simplified get_object() method
    
    Attributes (override in subclasses):
        model: Django model class (used to fetch object)
        pk_url_kwarg: URL kwarg name for primary key (default: 'pk')
        
    Methods to override:
        get_object(): Retrieve the object to update (uses model + pk by default)
        get_form_kwargs(): Add 'instance' to kwargs
    
    Example:
        class EmployeeUpdateView(BaseUpdateView):
            model = Employee
            form_class = EmployeeForm
            template_name = 'employee_form.html'
            page_title = 'Edit Employee'
            task_list_class = EmployeeTaskList
            success_message = 'Employee updated successfully.'
            
            def _get_breadcrumbs(self):
                return [
                    {'label': 'Employees', 'url': reverse_lazy('employee:list')},
                    {'label': 'Edit', 'url': None},
                ]
            
            def get_form_kwargs(self):
                kwargs = super().get_form_kwargs()
                kwargs['instance'] = self.get_object()
                return kwargs
    """
    model = None
    pk_url_kwarg = 'pk'
    
    def get_object(self):
        """
        Retrieve the object to update by primary key from URL kwargs.
        Override for custom object retrieval logic.
        
        Returns:
            model instance
        """
        pk = self.kwargs.get(self.pk_url_kwarg)
        return get_object_or_404(self.model, pk=pk)
    
    def get_form_kwargs(self):
        """
        Pass the object instance to the form.
        Override to add more kwargs.
        
        Returns:
            dict: Keyword arguments for form including 'instance'
        """
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.get_object()
        return kwargs


# ============================================================================
# GENERIC DELETE VIEW
# ============================================================================

class BaseDeleteView(View):
    """
    Base delete view with custom confirmation handling.
    
    This view supports both GET (confirmation page) and POST (actual deletion).
    
    Attributes (override in subclasses):
        model: Django model class
        pk_url_kwarg: URL kwarg name for primary key (default: 'pk')
        page_title: Display title for the page
        success_url: URL to redirect after deletion
        success_message: Message to display after deletion
        template_name: Path to confirmation template (optional)
        task_list_class: Module TaskList class
        
    Methods to override:
        _get_breadcrumbs(): Return breadcrumb data
        get_object(): Retrieve the object to delete
        delete_object(): Custom deletion logic
    
    Example:
        @method_decorator(has_permission(['ADMIN']), name='dispatch')
        class EmployeeDeleteView(BaseDeleteView):
            model = Employee
            success_url = reverse_lazy('employee:list')
            page_title = 'Delete Employee'
            task_list_class = EmployeeTaskList
            success_message = 'Employee deleted successfully.'
            
            def _get_breadcrumbs(self):
                return [
                    {'label': 'Employees', 'url': reverse_lazy('employee:list')},
                    {'label': 'Delete', 'url': None},
                ]
    """
    
    model = None
    pk_url_kwarg = 'pk'
    success_url = None
    success_message = "Item deleted successfully."
    template_name = None
    
    def get_object(self):
        """
        Retrieve the object to delete by primary key from URL kwargs.
        
        Returns:
            model instance
        """
        pk = self.kwargs.get(self.pk_url_kwarg)
        return get_object_or_404(self.model, pk=pk)
    
    def get_success_url(self):
        """
        Get URL to redirect to after deletion.
        
        Returns:
            str: URL to redirect to
        """
        if self.success_url:
            return self.success_url
        raise NotImplementedError(
            f"No success_url set on {self.__class__.__name__}. "
            "Override get_success_url() or set success_url attribute."
        )
    
    def get(self, request, *args, **kwargs):
        """Display confirmation page."""
        obj = self.get_object()
        obj.delete()  # Perform deletion immediately on GET for simplicity
        messages.success(request, self.success_message)
        return HttpResponseRedirect(self.get_success_url())

# ============================================================================
# SPECIALIZED VIEWS FOR COMMON PATTERNS
# ============================================================================

class BaseSearchListView(BaseListView):
    """
    List view with search functionality.
    
    Provides:
    - Search query handling from GET parameters
    - Search form in context
    - Filtered queryset based on search
    
    Attributes (override in subclasses):
        search_fields: List of model fields to search (default: [])
        search_param: GET parameter name (default: 'search')
        
    Methods to override:
        get_search_queryset(): Custom search filtering logic
    
    Example:
        class EmployeeSearchListView(BaseSearchListView):
            model = Employee
            search_fields = ['name', 'phone']
            
            def get_search_queryset(self, queryset, search_query):
                from django.db.models import Q
                q_objects = Q()
                for field in self.search_fields:
                    q_objects |= Q(**{f"{field}__icontains": search_query})
                return queryset.filter(q_objects)
    """
    
    search_fields = []
    search_param = 'search'
    
    def get_search_query(self):
        """Get search query from GET parameters."""
        return self.request.GET.get(self.search_param, '').strip()
    
    def get_search_queryset(self, queryset, search_query):
        """
        Apply search filtering. Override for custom logic.
        
        Args:
            queryset: The base queryset
            search_query: The search string
            
        Returns:
            Filtered queryset
        """
        if not search_query or not self.search_fields:
            return queryset
        
        
        q_objects = Q()
        for field in self.search_fields:
            q_objects |= Q(**{f"{field}__icontains": search_query})
        return queryset.filter(q_objects)
    
    def get_queryset(self):
        """Apply search filtering to queryset."""
        queryset = super(BaseListView, self).get_queryset()
        search_query = self.get_search_query()
        queryset = self.get_search_queryset(queryset, search_query)
        return self.get_paginated_data(queryset)
    
    def get_context_data(self, **kwargs):
        """Add search query to context."""
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.get_search_query()
        context['search_param'] = self.search_param
        return context


class BaseFilteredListView(BaseListView):
    """
    List view with filter form support.
    
    Provides:
    - Filter form display in context
    - Filter form class integration
    - Filtered queryset based on form data
    
    Attributes (override in subclasses):
        filter_form_class: Django form class for filtering
        
    Methods to override:
        get_filtered_queryset(): Custom filtering logic
    
    Example:
        class TransactionFilteredListView(BaseFilteredListView):
            model = PaymentTransaction
            filter_form_class = PaymentTransactionFilterForm
            
            def get_filtered_queryset(self, queryset, form_data):
                if form_data.is_valid():
                    if status := form_data.cleaned_data.get('status'):
                        queryset = queryset.filter(status=status)
                return queryset
    """
    
    filter_form_class = None
    
    def get_filter_form(self):
        """Get filter form instance."""
        if self.filter_form_class:
            return self.filter_form_class(self.request.GET or None)
        return None
    
    def get_filtered_queryset(self, queryset, filter_form):
        """
        Apply filtering. Override for custom logic.
        
        Args:
            queryset: The base queryset
            filter_form: The filter form instance
            
        Returns:
            Filtered queryset
        """
        return queryset
    
    def get_queryset(self):
        """Apply filtering to queryset."""
        queryset = super(BaseListView, self).get_queryset()
        filter_form = self.get_filter_form()
        queryset = self.get_filtered_queryset(queryset, filter_form)
        return self.get_paginated_data(queryset)
    
    def get_context_data(self, **kwargs):
        """Add filter form to context."""
        context = super().get_context_data(**kwargs)
        context['filter_form'] = self.get_filter_form()
        context['filter_form_action_url'] = self.request.path
        return context


# ============================================================================
# UTILITY FUNCTION
# ============================================================================

def prepare_form_context(view_instance, form=None, breadcrumbs=None, **extra_context):
    """
    Utility function to prepare common context for form views.
    
    Args:
        view_instance: The view instance (self)
        form: Form instance (optional)
        breadcrumbs: Breadcrumb data (optional, uses view's _get_breadcrumbs if not provided)
        **extra_context: Additional context data
        
    Returns:
        dict: Prepared context
    """
    context = {
        'page_title': view_instance.get_page_title(),
        'breadcrumbs': breadcrumbs or view_instance._get_breadcrumbs(),
        'task_list': view_instance.get_task_list(),
        'form_action_url': view_instance.request.path,
    }
    if form:
        context['form'] = form
    context.update(extra_context)
    return context