import itertools
import json
import logging

from django import template
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import permission_required, login_required

from .models import PatternAnswer, PatternQuestion, CacheAccessResult, CachePattern, CacheParameters, ParameterQuestion, ParameterAnswer, all_cache_question_parameters

logger = logging.getLogger('cachelabweb')



@login_required
def index_page(request):
    user = request.user.get_username()
    last_parameter_question = ParameterQuestion.last_for_user(user)
    last_parameter_answer = ParameterAnswer.last_for_question_and_user(last_parameter_question, user)
    if last_parameter_answer != None:
        last_parameter_in_progress = not last_parameter_answer.was_complete
    else:
        last_parameter_in_progress = False
    num_parameter_answer = ParameterAnswer.num_complete_for_user(user)
    best_parameter_answers = ParameterAnswer.best_K_for_user(user, 3)
    parameter_perfect_count = 0
    for answer in best_parameter_answers:
        if answer.score == answer.max_score:
            parameter_perfect_count += 1
    last_pattern_question = PatternQuestion.last_for_user(user)
    last_pattern_answer = PatternAnswer.last_for_question_and_user(last_pattern_question, user)
    if last_pattern_answer != None and last_pattern_answer.question == last_pattern_question:
        last_pattern_in_progress = not last_pattern_answer.was_complete
    else:
        last_pattern_in_progress = False
    num_pattern_answer = PatternAnswer.num_complete_for_user(user)
    if num_pattern_answer > 0:
        best_pattern_answer = PatternAnswer.best_complete_for_user()
        pattern_score = best_pattern_answer.score
        pattern_max_score = best_pattern_answer.max_score
    else:
        pattern_score = None
        pattern_max_score = None
    context = {
        'user': request.user.get_username(),
        'parameter_in_progress': last_parameter_in_progress,
        'parameter_complete': num_parameter_answer,
        'parameter_perfect_count':  parameter_perfect_count,
        'parameter_perfect': parameter_perfect_count >= 3,

        'pattern_complete': num_pattern_answer,
        'pattern_in_progress': last_pattern_in_progress,
        'pattern_score': pattern_score,
        'pattern_max_score': pattern_max_score,
        'pattern_perfect': pattern_score != None and pattern_score == pattern_max_score,

        'staff': request.session.get('is_staff', False),
    }
    for i, answer in enumerate(best_parameter_answers):
        context['parameter_score{}'.format(i+1)] = answer.score
        context['parameter_score{}_max'.format(i+1)] = answer.max_score
    return HttpResponse(render(request, 'quiz/user_index.html', context))

@login_required
def last_pattern_question(request):
    question = PatternQuestion.last_for_user(request.user.get_username())
    if not question:
        parameters = CacheParameters()
        parameters.save()
        PatternQuestion.generate_random(parameters=parameters, for_user=request.user.get_username())
        question = PatternQuestion.last_for_user(request.user.get_username())
    return pattern_question_detail(request, question.question_id)

@login_required
@require_http_methods(["POST"])
def new_pattern_question(request):
    parameters = CacheParameters.objects.first()
    if parameters == None:
        parameters = CacheParameters()
        parameters.save()
    PatternQuestion.generate_random(parameters=parameters, for_user=request.user.get_username())
    return redirect('last-pattern-question')

# FIXME: @permission_required('quiz.delete_patternquestion')
def test_control(request):
    return HttpResponse(render(request, 'quiz/test_control.html', {}))

def pattern_question_detail(request, question_id):
    question = PatternQuestion.objects.get(question_id=question_id)
    if question.for_user != request.user.get_username():
        raise PermissionDenied()
    answer = PatternAnswer.last_for_question_and_user(question, request.user.get_username())
    empty_access = CacheAccessResult.empty()
    is_given = itertools.chain([True] * question.give_first, itertools.cycle([False]))
    if answer:
        accesses_with_default = zip(question.pattern.accesses, answer.access_results, question.pattern.access_results, is_given)
    else:
        old_answers = [empty_access] * len(question.pattern.accesses)
        for i in range(question.give_first):
            old_answers[i] = question.pattern.access_results[i]
        accesses_with_default = zip(question.pattern.accesses, old_answers, question.pattern.access_results, is_given)
    accesses_with_default = list(accesses_with_default)
    widths = int((max(question.tag_bits, question.offset_bits, question.index_bits) + 3) / 4)
    context = {
        'question': question,
        'answer': answer,
        'accesses_with_default_and_correct_and_given': accesses_with_default,
        'show_correct': True if answer and answer.was_complete else False,
        'show_invalid': True if answer and not answer.was_complete and not answer.was_save else False,
        'tag_width': widths,
        'offset_width': widths,
        'index_width': widths,
        'ask_evict': question.ask_evict,
        'give_first': question.give_first,
        'debug_enable': False,
        'user': request.user.get_username(),
    }
    return HttpResponse(render(request, 'quiz/pattern_question.html', context))

def value_from_hex(x):
    if x != None and (x.startswith('0x') or x.startswith('0X')):
        x = x[2:]
    try:
        return int(x, 16)
    except ValueError:
        return None
    except TypeError:
        return None

def pattern_answer(request, question_id):
    question = get_object_or_404(PatternQuestion, question_id=question_id)
    if question.for_user != request.user.get_username():
        raise PermissionDenied()
    last_answer = PatternAnswer.last_for_question_and_user(question, request.user.get_username())
    if last_answer and last_answer.was_complete:  # FIXME: threshold?
        return HttpResponse("You already submitted an answer to this question.")
    answer = PatternAnswer()
    answer.question = question
    submitted_results = []
    is_complete = True
    parts = ['tag', 'index', 'offset']
    if question.ask_evict:
        parts.append('evicted')
    logger.debug('POST request is %s', request.POST)
    for i in range(question.give_first):
        submitted_results.append(question.pattern.access_results[i])
    for i in range(question.give_first, len(question.pattern.access_results)):
        cur_access = CacheAccessResult()
        hit_key = 'access_hit_{}'.format(i)
        if hit_key in request.POST:
            hit_value = request.POST[hit_key]
        else:
            cur_access.set_invalid('hit')
        if hit_value == 'hit':
            cur_access.set_bool('hit', True)
        elif hit_value != None and hit_value.startswith('miss'):
            cur_access.set_bool('hit', False)
        else:
            cur_access.set_bool('hit', None)
        for which in ['tag', 'index', 'offset']:
            key = 'access_{}_{}'.format(which, i)
            if key in request.POST:
                value = request.POST[key].strip()
            else:
                value = ''
            value_invalid = cur_access.set_from_string(which, value)
            is_complete = is_complete and value_invalid
        if hit_value != 'miss-evict':
            cur_access.set_from_string('evicted', '')
            cur_access.evicted.invalid = False
        else:
            value = request.POST.get('access_evicted_{}'.format(i), '')
            value_invalid = cur_access.set_from_string('evicted', value)
            is_complete = is_complete and value_invalid
        logger.debug('adding access %s', cur_access)
        submitted_results.append(cur_access)
    answer.access_results = submitted_results
    answer.for_user = request.user.get_username()
    answer.was_complete = is_complete
    if request.POST.get('is_save'):
        answer.was_save = True
        answer.was_complete = False
    answer.save()
    if answer.was_complete or answer.was_save:
        return redirect('user-index')
    elif PatternQuestion.last_for_user(request.user.get_username()) == question:
        return redirect('last-pattern-question')
    else:
        return redirect('pattern-question', question.question_id)

def _name_parameter(parameter):
    if parameter.startswith('num_'):
        return 'number of ' + parameter[len('num_'):]
    elif parameter.endswith('_bits'):
        return parameter[:-len('_bits')] + ' bits'
    elif parameter == 'way_size_bytes':
        return 'total bytes per way'
    elif parameter == 'set_size_bytes':
        return 'total bytes per set'
    elif parameter.endswith('_bytes'):
        return parameter[:-len('_bytes')].replace('_', ' ') + ' (bytes)'
    elif parameter == 'block_size':
        return 'block size (bytes)'
    else:
        return parameter

def format_value_with_postfix(value):
    if value > 1024 * 1024 * 1024 and value % (1024 * 1024 * 1024) == 0:
        return '%dG' % (value / (1024 * 1024 * 1024))
    elif value > 1024 * 1024 and value % (1024 * 1024) == 0:
        return '%dM' % (value / (1024 * 1024))
    elif value > 1024 and value % (1024) == 0:
        return '%dK' % (value / (1024))
    else:
        return '%d' % (value)

@login_required
def parameter_question_detail(request, question_id):
    question = get_object_or_404(ParameterQuestion, question_id=question_id)
    if question.for_user != request.user.get_username():
        raise PermissionDenied()
    last_answer = ParameterAnswer.last_for_question_and_user(question, request.user.get_username())
    params = []
    if last_answer:
        mark_invalid = not last_answer.was_complete and not last_answer.was_save
        show_correct = last_answer.was_complete
        logger.debug('mark_invalid = %s; show_correct = %s', mark_invalid, show_correct)
    else:
        mark_invalid = False
        show_correct = False
    for item in all_cache_question_parameters:
        if item in question.given_parts:
            value = format_value_with_postfix(question.find_cache_property(item))
            correct_p = True
            invalid_p = False
            given_p = True
        elif item in question.missing_parts:
            if last_answer:
                value = last_answer.answer.get(item, '')
                correct_p = last_answer.answer.get(item + '_correct', False)
                invalid_p = last_answer.answer.get(item + '_invalid', True)
            else:
                value = ''
                correct_p = False
                invalid_p = True
            given_p = False
        current = {
            'id': item,
            'name': _name_parameter(item),
            'value': value,
            'correct': correct_p,
            'invalid': invalid_p,
            'given': given_p,
            'correct_value': format_value_with_postfix(question.find_cache_property(item)),
        }
        params.append(current)
    context = {
        'show_correct': show_correct,
        'mark_invalid': mark_invalid,
        'params': params,
        'question': question,
        'answer': last_answer,
    }
    return HttpResponse(render(request, 'quiz/parameter_question.html', context))

@login_required
@require_http_methods(["POST"])
def parameter_answer(request, question_id):
    question = get_object_or_404(ParameterQuestion, question_id=question_id)
    if question.for_user != request.user.get_username():
        raise PermissionDenied()
    answer = ParameterAnswer()
    answer.question = question
    answer.for_user = request.user.get_username()
    answer.set_answer_from_post(request.POST)
    if request.POST.get('is_save', '') != '':
        answer.was_complete = False
        answer.was_save = True
    else:
        answer.was_save = False
    answer.save()
    if answer.was_save:
        logger.info('was save')
        return redirect('user-index')
    else:
        logger.info('was not save')
        return redirect('last-parameter-question')

@login_required
@require_http_methods(["POST"])
def new_parameter_question(request):
    question = ParameterQuestion.generate_new(request.user.get_username())
    return redirect('last-parameter-question')

@login_required
def last_parameter_question(request):
    question = ParameterQuestion.last_for_user(request.user.get_username())
    if not question:
        question = ParameterQuestion.generate_new(request.user.get_username())
    return parameter_question_detail(request, question.question_id)

# FIXME: make admin only
@require_http_methods(["POST"])
#@permission_required('quiz.delete_patternquestion')
def clear_all_questions(request):
    if PatternQuestion.objects.filter(~Q(for_user__exact='guest') & ~Q(for_user__exact='test')).count() == 0:
        PatternAnswer.objects.all().delete()
        PatternQuestion.objects.all().delete()
        ParameterAnswer.objects.all().delete()
        ParameterQuestion.objects.all().delete()
        CachePattern.objects.all().delete()
        CacheParameters.objects.all().delete()
        return HttpResponse("Cleared all questions.")
    else:
        return HttpResponse("Refusing to clear all questions.")

@login_required
@require_http_methods(["POST"])
def forget_questions(request):
    if request.session.get('is_staff', False) == False:
        return HttpResponse('This feature is for staff only.')
    else:
        user = request.user.get_username()
        hidden_user = user + '+hidden'
        PatternAnswer.objects.filter(for_user__exact=user).update(for_user=hidden_user)
        PatternQuestion.objects.filter(for_user__exact=user).update(for_user=hidden_user)
        ParameterAnswer.objects.filter(for_user__exact=user).update(for_user=hidden_user)
        ParameterQuestion.objects.filter(for_user__exact=user).update(for_user=hidden_user)
        return HttpResponse('questions forgotten')

@login_required
@require_http_methods(["POST"])
def unforget_questions(request):
    if request.session.get('is_staff', False) == False:
        return HttpResponse('This feature is for staff only.')
    else:
        user = request.user.get_username()
        hidden_user = user + '+hidden'
        PatternAnswer.objects.filter(for_user__exact=hidden_user).update(for_user=user)
        PatternQuestion.objects.filter(for_user__exact=hidden_user).update(for_user=user)
        ParameterAnswer.objects.filter(for_user__exact=hidden_user).update(for_user=user)
        ParameterQuestion.objects.filter(for_user__exact=hidden_user).update(for_user=user)
        return HttpResponse('questions unforgotten')


