from django.core.paginator import Paginator


class PaginationMixin:
    """
    Provides `paginate_queryset(request, queryset, page_size, mode)` returning
    `(page_or_serialized, meta)` where `meta` contains pagination info for templates.
    """

    def paginate_queryset(self, request, queryset, page_size=20, mode="template"):
        paginator = Paginator(queryset, page_size)
        page_number = request.GET.get("page", 1)
        page = paginator.get_page(page_number)
        meta = {
            "page": page.number,
            "page_size": page_size,
            "total_pages": paginator.num_pages,
            "total_items": paginator.count,
            "has_next": page.has_next(),
            "has_previous": page.has_previous(),
            "next_page": page.next_page_number() if page.has_next() else None,
            "previous_page": page.previous_page_number() if page.has_previous() else None,
        }
        return page, meta
