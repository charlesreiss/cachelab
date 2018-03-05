from django.urls import path

from . import views

urlpatterns = [
    path('', views.quiz, name='quiz'),
    path('submit-cache-answer/<question_id>', views.cache_answer, name='cache_answer'),
]

