from django.contrib import admin

from .models import PatternQuestion, CachePattern, CacheParameters, PatternAnswer

admin.site.register(PatternQuestion)
admin.site.register(CachePattern)
admin.site.register(CacheParameters)
admin.site.register(PatternAnswer)
