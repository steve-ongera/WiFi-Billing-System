from django.urls import path
from . import views

urlpatterns = [
    path('', views.portal_login, name='portal_login'),
    path('select-plan/<int:plan_id>/', views.select_plan, name='select_plan'),
    path('payment/', views.payment_page, name='payment_page'),
    path('process-payment/', views.process_payment, name='process_payment'),
    path('internet-access/', views.internet_access, name='internet_access'),
]
