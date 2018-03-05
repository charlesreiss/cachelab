import itertools

from django import template
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import permission_required

from .models import PatternAnswer, PatternQuestion, CachePattern, CacheParameters

def quiz(request):
    question = PatternQuestion.last_question_for_user('test')
    if not question:
        PatternQuestion.generate_random(parameters=CacheParameters.objects.first(), for_user='test')
        question = PatternQuestion.last_question_for_user('test')
    return pattern_question_detail(request, PatternQuestion.last_question_for_user('test').question_id)

@require_http_methods(["POST"])
def new_pattern_question(request):
    name = 'test'
    PatternQuestion.generate_random(parameters=CacheParameters.objects.first(), for_user='test')
    return redirect('quiz')

def test_control(request):
    return HttpResponse(render(request, 'quiz/test_control.html', {}))
    
def pattern_question_detail(request, question_id):
    question = PatternQuestion.objects.get(question_id=question_id)
    answer = PatternAnswer.last_for_question(question)
    if answer:
        accesses_with_default = zip(question.pattern.accesses, answer.access_results, question.pattern.access_results)
    else:
        accesses_with_default = zip(question.pattern.accesses, itertools.cycle([False]), question.pattern.access_results)
    context = {
        'question': question,
        'answer': answer,
        'accesses_with_default_and_correct': accesses_with_default,
    }
    return HttpResponse(render(request, 'quiz/pattern_question.html', context))

def pattern_answer(request, question_id):
    question = get_object_or_404(PatternQuestion, question_id=question_id)
    last_answer = PatternAnswer.last_for_question(question)
    if last_answer:
        return HttpResponse("You already submitted an answer to this question.")
    answer = PatternAnswer()
    answer.question = question
    expected_results = question.pattern.access_results
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
    return redirect('quiz')

# FIXME: make admin only
@require_http_methods(["POST"])
@permission_required('quiz.delete_patternquestion')
def clear_all_questions(request):
    if PatternQuestion.objects.filter(~Q(for_user__exact='test')).count() == 0:
        PatternAnswer.objects.all().delete()
        PatternQuestion.objects.all().delete()
        CachePattern.objects.all().delete()
        CacheParameters.objects.all().delete()
        return HttpResponse("Cleared all questions.")
    else:
        return HttpResponse("Refusing to clear all questions.")

