from django.urls import path

from . import views

urlpatterns = [
    path('', views.quiz, name='quiz'),
    path('submit-pattern-answer/<question_id>', views.pattern_answer, name='pattern_answer'),
]

