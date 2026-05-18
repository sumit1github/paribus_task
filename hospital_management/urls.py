from django.urls import path

from . import views

app_name = 'hospital_management'

urlpatterns = [
    path('', views.HospitalListView.as_view(), name='list'),
    path('new/', views.HospitalNewFormView.as_view(), name='new'),
    path('new/cancel/', views.HospitalNewFormCancelView.as_view(), name='new_form_cancel'),
    path('create/', views.HospitalCreateView.as_view(), name='create'),
    path('<int:pk>/', views.HospitalRowView.as_view(), name='row'),
    path('<int:pk>/edit/', views.HospitalEditFormView.as_view(), name='edit'),
    path('<int:pk>/update/', views.HospitalUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.HospitalDeleteView.as_view(), name='delete'),
    path('<int:pk>/activate/', views.HospitalActivateView.as_view(), name='activate'),
]
