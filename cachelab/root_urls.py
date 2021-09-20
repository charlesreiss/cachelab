# URLs for when cachelab is used standalone;

from django.urls import path, include

urlpatterns = [
    path('', include('cachelab.urls')),
    path('', include('myauth.urls')),
]

