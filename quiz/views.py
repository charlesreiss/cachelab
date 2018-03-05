from django import template
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from .models import PatternAnswer, PatternQuestion, CacheParameters

def quiz(request):
    all_questions = PatternQuestion.objects.all()
    if len(all_questions) == 0:
        parameters = CacheParameters()
        parameters.save()
        the_question = PatternQuestion.generate_random(parameters, 'test', 0)
        the_question.save()
    else:
        the_question = all_questions[0]
    return pattern_question_detail(request, the_question.question_id)
    
def pattern_question_detail(request, question_id):
    question = PatternQuestion.objects.get(question_id=question_id)
    context = {
        'question': question,
    }
    return HttpResponse(render(request, 'quiz/cache_question.html', context))

def pattern_answer(request, question_id):
    question = get_object_or_404(Question, question_id=question_id)
    answer = PatternAnswer()
    answer.question = question
    expected_results = question.access_results
    actual_results = []
    for i in range(len(expected_results)):
        if 'access_hit_{}'.format(i) in request.POST:
            actual_results.append(True)
        else:
            actual_results.append(False)
    score = 0
    for actual, expected in zip(actual_results, expected_results):
        if actual == expected:
            score += 1
    answer.access_results = actual_results
    answer.score = score
    answer.save()
    return HttpResponse("Your score was {}.".format(answer.score)) 
