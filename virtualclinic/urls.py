"""virtualclinic URL Configuration"""
from django.contrib import admin
from django.urls import include, path, re_path

admin.autodiscover()

urlpatterns = [
    re_path(r'^admin/', admin.site.urls),
    re_path(r'^', include(('server.urls', 'server'), namespace='server')),
]