"""showcase 应用路由。"""

from django.urls import path

from . import views

app_name = 'showcase'

urlpatterns = [
    path('', views.home, name='home'),
    path('project/<slug:slug>/', views.detail, name='detail'),
]
