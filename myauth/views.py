from django import template
from django.conf import settings
from django.contrib.auth.models import User, UserManager
from django.contrib.auth import login, logout as django_logout, views as auth_views
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .models import StaffUser

import json
import hmac
import logging
import time

logger = logging.getLogger('cachelab')

class MyLoginView(auth_views.LoginView):
    def form_valid(self, form):
        result = super().form_valid(form)
        if StaffUser.objects.filter(user=form.get_user()):
            self.request.session['is_staff'] = 1
        return result

@require_http_methods(["POST"])
@csrf_exempt
def forwarded_login_setup(request):
    info = request.POST['info']
    actual_mac = request.POST['mac']
    mac = hmac.new(settings.SECRET_KEY.encode('UTF-8'), digestmod='SHA512')
    mac.update(info.encode('UTF-8'))
    if hmac.compare_digest(mac.hexdigest(), actual_mac):
        logger.debug('loading %s', info)
        data = json.loads(info)
        username = data['username']
        timestamp = int(data['timestamp'])
        offset = time.time() - timestamp
        if offset < 3600:
            request.session['allowed_logins'] = request.session.get('allowed_logins', []) + [username   ]
            if data.get('staff'):
                request.session['is_staff'] = int(data.get('staff', '0'))
            elif request.session.get('is_staff') != None:
                del request.session['is_staff']
            return redirect('forwarded-login-prompt', username)
        else:
            return HttpResponse("Login expired.", status=401)
    else:
        return HttpResponse(status=401)

def forwarded_login_prompt(request, username):
    logger.debug('session is %s', request.session.items())
    if request.user.get_username() == username:
        return redirect('/')
    elif username in request.session['allowed_logins']:
        return HttpResponse(render(request, 'login_prompt.html', {'username': username}))
    else:
        return HttpResponse(status=401)

def forwarded_login(request):
    username = request.POST['username']
    if username in request.session.get('allowed_logins', []):
        try:
            the_account = User.objects.get(username=username)
        except User.DoesNotExist:
            the_account = User.objects.create_user(username)
        login(request, the_account)
        if 'allowed_logins' in request.session:
            del request.session['allowed_logins']
        return redirect('/')
    else:
        return HttpReponse(status=401)

@require_http_methods(["POST"])
def logout(request):
    if 'allowed_logins' in request.session:
        del request.session['allowed_logins']
    if 'is_staff' in request.session:
        del request.session['is_staff']
    django_logout(request)
    if settings.COURSE_WEBSITE:
        return redirect(settings.COURSE_WEBSITE)
    else:
        return redirect('/')
