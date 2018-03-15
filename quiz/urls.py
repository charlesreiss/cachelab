from django.urls import path

from . import views

urlpatterns = [
    path('', views.index_page, name='user-index'),
    path('pattern-question', views.last_pattern_question, name='last-pattern-question'),
    path('pattern-question/<question_id>', views.pattern_question_detail, name='pattern-question'),
    path('submit-pattern-answer/<question_id>', views.pattern_answer, name='pattern-answer'),
    path('new-pattern-question', views.new_pattern_question, name='new-pattern-question'),
    path('test', views.test_control, name='test-control'),
    path('clear-all-questions', views.clear_all_questions, name='clear-all-questions'),
]

