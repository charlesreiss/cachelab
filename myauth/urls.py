from django.contrib import admin
from django.urls import include, path
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login-setup', views.forwarded_login_setup, name='forwarded-login-setup'),
    path('login-prompt/<username>', views.forwarded_login_prompt, name='forwarded-login-prompt'),
    path('login', views.forwarded_login, name='forwarded-login'),
    path('logout', views.logout , name='logout'),
    path('builtin-login/', views.MyLoginView.as_view(template_name='builtin_login.html'), name='builtin-login')
]
