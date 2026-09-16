"""virtualclinic URL Configuration"""
from django.contrib import admin
from django.urls import include, path, re_path
from django.urls import path, include

admin.autodiscover()

urlpatterns = [
    # 1. Include server.urls FIRST so custom /admin/ routes are checked first
    path('', include(('server.urls', 'server'), namespace='server')),

    # 2. Default Django Admin site LAST
    path('admin/', admin.site.urls),
]