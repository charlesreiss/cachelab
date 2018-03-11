import itertools
import json
import logging

from django import template
from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import permission_required, login_required

from .models import PatternAnswer, PatternQuestion, CachePattern, CacheParameters

logger = logging.getLogger('cachelabweb')

@login_required
def quiz(request):
    question = PatternQuestion.last_question_for_user(request.user.username)
    if not question:
        # FIXME : use existing
        parameters = CacheParameters()
        parameters.save()
        PatternQuestion.generate_random(parameters=parameters, for_user=request.user.username)
        question = PatternQuestion.last_question_for_user('test')
    return pattern_question_detail(request, PatternQuestion.last_question_for_user(request.user.username).question_id)

@login_required
@require_http_methods(["POST"])
def new_pattern_question(request):
    name = 'test'
    PatternQuestion.generate_random(parameters=CacheParameters.objects.first(), for_user='test')
    return redirect('quiz')

# FIXME: @permission_required('quiz.delete_patternquestion')
def test_control(request):
    return HttpResponse(render(request, 'quiz/test_control.html', {}))

    
def pattern_question_detail(request, question_id):
    question = PatternQuestion.objects.get(question_id=question_id)
    answer = PatternAnswer.last_for_question(question)
    empty_access = {
        'hit': None,
        'tag': '',
        'index': '',
        'offset': '',
        'tag_correct': None,
        'index_correct': None,
        'offset_correct': None,
        'hit_correct': None,
        'tag_invalid': True,
        'index_invalid': True,
        'offset_invalid': True,
        'hit_invalid': True,
        'evicted': None,
    }
    is_given = itertools.chain([True] * question.give_first, itertools.cycle([False]))
    if answer:
        accesses_with_default = zip(question.pattern.accesses, answer.access_results, question.pattern.access_results, is_given)
    else:
        old_answers = [empty_access] * len(question.pattern.accesses)
        for i in range(question.give_first):
            old_answers[i] = question.pattern.access_results[i].copy()
            for key in ['tag', 'index', 'offset', 'evicted']:
                old_answers[i][key + '_invalid'] = False
                if old_answers[i][key] != None:
                    old_answers[i][key] = '0x{:x}'.format(old_answers[i][key])
            old_answers[i]['hit_invalid'] = False
        accesses_with_default = zip(question.pattern.accesses, old_answers, question.pattern.access_results, is_given)
    widths = int((max(question.tag_bits, question.offset_bits, question.index_bits) + 3) / 4)
    context = {
        'question': question,
        'answer': answer,
        'accesses_with_default_and_correct_and_given': accesses_with_default,
        'show_correct': True if answer and answer.was_complete else False,
        'show_invalid': True if answer and not answer.was_complete else False,
        'tag_width': widths,
        'offset_width': widths,
        'index_width': widths,
        'ask_evict': question.ask_evict,
        'give_first': question.give_first,
        'debug_enable': False,
    }
    return HttpResponse(render(request, 'quiz/pattern_question.html', context))

def _convert_value(x):
    if x != None and (x.startswith('0x') or x.startswith('0X')):
        x = x[2:]
    try:
        return hex(x)
    except TypeError:
        return None

def pattern_answer(request, question_id):
    question = get_object_or_404(PatternQuestion, question_id=question_id)
    last_answer = PatternAnswer.last_for_question(question)
    if last_answer and last_answer.was_complete:  # FIXME: threshold?
        return HttpResponse("You already submitted an answer to this question.")
    answer = PatternAnswer()
    answer.question = question
    expected_results = question.pattern.access_results
    submitted_results = []
    is_complete = True
    parts = ['tag', 'index', 'offset']
    if question.ask_evict:
        parts.append('evicted')
    for i in range(len(expected_results)):
        cur_access = {
            'hit': False,
            'tag': None,
            'index': None,
            'offset': None,
            'evicted': None,
        }
        hit_key = 'access_hit_{}'.format(i)
        if hit_key in request.POST:
            hit_value = request.POST[hit_key]
            cur_access['hit_invalid'] = False
        else:
            hit_value = None
            cur_access['hit_invalid'] = True
        if hit_value == 'hit':
            cur_access['hit'] = True
        elif hit_value != None and hit_value.startswith('miss'):
            cur_access['hit'] = False
        else:
            cur_access['hit'] = None
        for which in ['tag', 'index', 'offset', 'evicted']:
            key = 'access_{}_{}'.format(which, i)
            if key in request.POST:
                value = request.POST[key].strip()
                cur_access[which] = value
                if _convert_value(value) == None:
                    cur_access[which + '_invalid'] = True
                    is_complete = False
                else:
                    cur_access[which + '_invalid'] = False
            else:
                is_complete = False
        if hit_value != 'miss-evict':
            cur_access['evicted'] = None
            cur_access['evicted_invalid'] = False
        else:
            if cur_access['evicted'] == None:
                cur_access['evicted'] = ''
                cur_access['evicted_invalid'] = True
                is_complete = False
            elif _convert_value(cur_access['evicted']) == None:
                cur_access['evicted_invalid'] = TRue
                is_complete = False
        submitted_results.append(cur_access)
    score = 0
    i = 0
    for submitted, expected in zip(submitted_results, expected_results):
        if submitted['hit'] == expected['hit']:
            if i >= question.give_first:
                score += 1
            submitted['hit_correct'] = True
            logger.debug("Setting hit_correct TRUE")
        else:
            submitted['hit_correct'] = False
            logger.debug("Setting hit_correct FALSE")
        for which in ['tag', 'index', 'offset']:
            if _convert_value(submitted[which]) == expected[which]:
                submitted[which + '_correct'] = True
                if i >= question.give_first:
                    score += 1
            else:
                submitted[which + '_correct'] = False
        i += 1
    answer.access_results = submitted_results
    answer.was_complete = is_complete
    answer.score = score
    answer.save()
    return redirect('quiz')

# FIXME: make admin only
@require_http_methods(["POST"])
#@permission_required('quiz.delete_patternquestion')
def clear_all_questions(request):
    if PatternQuestion.objects.filter(~Q(for_user__exact='guest') & ~Q(for_user__exact='test')).count() == 0:
        PatternAnswer.objects.all().delete()
        PatternQuestion.objects.all().delete()
        CachePattern.objects.all().delete()
        CacheParameters.objects.all().delete()
        return HttpResponse("Cleared all questions.")
    else:
        return HttpResponse("Refusing to clear all questions.")

