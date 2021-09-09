"""cachelabweb URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login-setup', views.forwarded_login_setup, name='forwarded-login-setup'),
    path('login-prompt/<username>', views.forwarded_login_prompt, name='forwarded-login-prompt'),
    path('login', views.forwarded_login, name='forwarded-login'),
    path('logout', views.logout , name='logout'),
    path('', include('cachelab.exercises.urls')),
    path('builtin-login/', auth_views.LoginView.as_view(template_name='builtin_login.html'), name='builtin-login')
]