from django.contrib import admin

from .models import CacheQuestion, CachePattern, CacheParameters, CacheAnswer

admin.site.register(CacheQuestion)
admin.site.register(CachePattern)
admin.site.register(CacheParameters)
admin.site.register(CacheAnswer)
