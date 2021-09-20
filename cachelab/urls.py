# URLs for cachelab exercises in a way which can be included in a larger project;
# if running this standalone use root_urls instead

from django.urls import path

from . import views

urlpatterns = [
    path('', views.index_page, name='user-index'),
    path('pattern-question', views.last_pattern_question, name='last-pattern-question'),
    path('pattern-question/<question_id>', views.pattern_question_detail, name='pattern-question'),
    path('submit-pattern-answer/<question_id>', views.pattern_answer, name='pattern-answer'),
    path('new-pattern-question', views.new_pattern_question, name='new-pattern-question'),

    path('parameter-question', views.last_parameter_question, name='last-parameter-question'),
    path('parameter-question/<question_id>', views.parameter_question_detail, name='parameter-question'),
    path('submit-parameter-answer/<question_id>', views.parameter_answer, name='parameter-answer'),
    path('new-parameter-question', views.new_parameter_question, name='new-parameter-question'),

    path('test', views.test_control, name='test-control'),
    path('clear-all-questions', views.clear_all_questions, name='clear-all-questions'),
    
    path('forget-questions', views.forget_questions, name='forget-questions'),
    path('unforget-questions', views.unforget_questions, name='unforget-questions'),

    path('scores.csv', views.get_scores_csv, name='scores-csv'),
]

