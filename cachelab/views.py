import csv
import datetime
import itertools
import json
import logging

from django import template
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import permission_required, login_required


from .models import PatternAnswer, PatternQuestion, CacheAccessResult, CachePattern, CacheParameters, ParameterQuestion, ParameterAnswer, ResultItem, all_cache_question_parameters, random_parameters_for_pattern, extract_best_for_user

logger = logging.getLogger('cachelabweb')

NEEDED_PARAMETER_PERFECT = 3

def request_is_staff(request):
    return (
        request.session.get('cachelab_is_staff') == 1 or
        request.session.get('is_staff') == 1
    )

def staff_required(wrapped_function):
    def real_function(request, *args, **named_args):
        if not request_is_staff(request):
            return HttpResponse('This feature is for staff only.', status_code=403)
        else:
            return wrapped_function(request, *args, **named_args)
    return login_required(real_function)

def pattern_perfect(request):
    user = request.user.get_username()
    best_pattern_answer = PatternAnswer.best_complete_for_user(request.user.get_username())
    if best_pattern_answer != None:
        return best_pattern_answer.score == best_pattern_answer.max_score
    else:
        return False

def parameter_perfect(request):
    user = request.user.get_username()
    parameter_perfect_count = 0
    best_parameter_answers = ParameterAnswer.best_K_for_user(user, NEEDED_PARAMETER_PERFECT)
    for answer in best_parameter_answers:
        if answer.score == answer.max_score:
            parameter_perfect_count += 1
    return parameter_perfect_count >= NEEDED_PARAMETER_PERFECT

def _fill_context(request, context):
    context.update({
        'user': request.user.get_username(),
        'staff': request_is_staff(request),
        'course_website': settings.COURSE_WEBSITE,
        'debug_enable': request_is_staff(request) and request.GET.get('debug', 'false') == 'true',
    })
    return context

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
    best_parameter_answers = ParameterAnswer.best_K_for_user(user, NEEDED_PARAMETER_PERFECT)
    parameter_perfect_count = 0
    for answer in best_parameter_answers:
        if answer.score == answer.max_score:
            parameter_perfect_count += 1
    last_pattern_question = PatternQuestion.last_for_user(user)
    last_pattern_answer = PatternAnswer.last_for_question_and_user(last_pattern_question, user)
    if last_pattern_answer != None and last_pattern_answer.question == last_pattern_question:
        last_pattern_in_progress = not last_pattern_answer.was_complete
    elif last_pattern_question != None:
        last_pattern_in_progress = True
    else:
        last_pattern_in_progress = False
    num_pattern_answer = PatternAnswer.num_complete_for_user(user)
    if num_pattern_answer > 0:
        best_pattern_answer = PatternAnswer.best_complete_for_user(user)
        pattern_score = best_pattern_answer.score
        pattern_max_score = best_pattern_answer.max_score
    else:
        pattern_score = None
        pattern_max_score = None
    context = _fill_context(request, {
        'parameter_in_progress': last_parameter_in_progress,
        'parameter_complete': num_parameter_answer,
        'parameter_perfect_count':  parameter_perfect_count,
        'parameter_perfect': parameter_perfect_count >= NEEDED_PARAMETER_PERFECT,

        'pattern_complete': num_pattern_answer,
        'pattern_in_progress': last_pattern_in_progress,
        'pattern_score': pattern_score,
        'pattern_max_score': pattern_max_score,
        'pattern_perfect': pattern_score != None and pattern_score == pattern_max_score,
    })
    for i, answer in enumerate(best_parameter_answers):
        context['parameter_score{}'.format(i+1)] = answer.score
        context['parameter_score{}_max'.format(i+1)] = answer.max_score
    return HttpResponse(render(request, 'exercises/user_index.html', context))

@login_required
def list_pattern_questions(request):
    user = request.user.get_username()
    all_questions = PatternQuestion.objects.filter(for_user__exact=user).order_by('-index')
    context = _fill_context(request, {})
    lst = []
    for question in all_questions:
        lst.append((
            question,
            PatternAnswer.last_for_question_and_user(question, user)
        ))
    context['old_questions'] = lst
    return HttpResponse(render(request, 'exercises/pattern_question_list.html', context))

@login_required
def last_pattern_question(request):
    question = PatternQuestion.last_for_user(request.user.get_username())
    if not question:
        PatternQuestion.generate_random(
            parameters=random_parameters_for_pattern(), for_user=request.user.get_username()
        )
        question = PatternQuestion.last_for_user(request.user.get_username())
    return pattern_question_detail(request, question.question_id)

@login_required
@require_http_methods(["POST"])
def new_pattern_question(request):
    parameters = random_parameters_for_pattern()
    PatternQuestion.generate_random(parameters=parameters, for_user=request.user.get_username())
    return redirect('last-pattern-question')

# FIXME: @permission_required('quiz.delete_patternquestion')
def test_control(request):
    return HttpResponse(render(request, 'exercises/test_control.html', {}))

def pattern_question_detail(request, question_id):
    question = PatternQuestion.objects.get(question_id=question_id)
    if question.for_user != request.user.get_username():
        raise PermissionDenied()
    latest_question = PatternQuestion.last_for_user(request.user.get_username())
    show_old = latest_question.question_id != question.question_id
    have_old = latest_question.index > 0
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
    widths = int((max(question.tag_bits, question.offset_bits, question.index_bits) + 3) / 4) + 3
    address_width = int((question.address_bits + 3) / 4) + 3
    context = _fill_context(request, {
        'question': question,
        'answer': answer,
        'accesses_with_default_and_correct_and_given': accesses_with_default,
        'show_correct': True if answer and answer.was_complete else False,
        'show_invalid': True if answer and not answer.was_complete and not answer.was_save else False,
        'tag_width': widths,
        'offset_width': widths,
        'index_width': widths,
        'evicted_width': address_width,
        'ask_evict': question.ask_evict,
        'give_first': question.give_first,
        'pattern_perfect': pattern_perfect(request),
        'parameter_perfect': parameter_perfect(request),
        'show_old': show_old,
        'have_old': have_old,
    })
    return HttpResponse(render(request, 'exercises/pattern_question.html', context))

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
            if hit_value == 'hit':
                cur_access.set_bool('hit', True)
            elif hit_value != None and hit_value.startswith('miss'):
                cur_access.set_bool('hit', False)
            else:
                cur_access.set_bool('hit', None)
        else:
            hit_value = None
            cur_access.set_invalid('hit')
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
    if answer.was_save:
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
        return 'total data bytes per way'
    elif parameter == 'set_size_bytes':
        return 'total data bytes per set'
    elif parameter.endswith('_bytes'):
        return parameter[:-len('_bytes')].replace('_', ' ') + ' (bytes)'
    elif parameter == 'block_size':
        return 'block size (bytes)'
    else:
        return parameter

def format_value_with_postfix(value):
    if value > 1024 * 1024 * 1024 and value % (1024 * 1024 * 1024) == 0:
        return '%dG (= %d)' % (value / (1024 * 1024 * 1024), value)
    elif value > 1024 * 1024 and value % (1024 * 1024) == 0:
        return '%dM (= %d)' % (value / (1024 * 1024), value)
    elif value > 1024 and value % (1024) == 0:
        return '%dK (= %d)' % (value / (1024), value)
    else:
        return '%d' % (value)


@login_required
def parameter_question_detail(request, question_id):
    question = get_object_or_404(ParameterQuestion, question_id=question_id)
    user = request.user.get_username()
    if question.for_user != user:
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
            value = ResultItem(
                value=question.find_cache_property(item),
                string=format_value_with_postfix(question.find_cache_property(item)),
                correct=True,
                invalid=False,
            )
            given_p = True
        elif item in question.missing_parts:
            given_p = False
            if last_answer:
                value = last_answer.answer.get(item)
            else:
                value = ResultItem.empty_invalid()
        else:
            continue
        current = {
            'id': item,
            'name': _name_parameter(item),
            'value': value,
            'given': given_p,
            'correct_value': format_value_with_postfix(question.find_cache_property(item)),
        }
        params.append(current)
    best_parameter_answers = ParameterAnswer.best_K_for_user(user, 3)
    parameter_perfect_count = 0
    for answer in best_parameter_answers:
        if answer.score == answer.max_score:
            parameter_perfect_count += 1
    context = _fill_context(request, {
        'show_correct': show_correct,
        'mark_invalid': mark_invalid,
        'params': params,
        'question': question,
        'answer': last_answer,

        'num_perfect': parameter_perfect_count,
        'perfect': parameter_perfect_count >= NEEDED_PARAMETER_PERFECT,
        'needed_perfect': NEEDED_PARAMETER_PERFECT,
        'remaining_perfect': NEEDED_PARAMETER_PERFECT - parameter_perfect_count,

        'pattern_perfect': pattern_perfect(request),
    })
    return HttpResponse(render(request, 'exercises/parameter_question.html', context))

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

@require_http_methods(["POST"])
@staff_required
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

@staff_required
@require_http_methods(["POST"])
def forget_questions(request):
    user = request.user.get_username()
    hidden_user = user + '+hidden'
    PatternAnswer.objects.filter(for_user__exact=user).update(for_user=hidden_user)
    PatternQuestion.objects.filter(for_user__exact=user).update(for_user=hidden_user)
    ParameterAnswer.objects.filter(for_user__exact=user).update(for_user=hidden_user)
    ParameterQuestion.objects.filter(for_user__exact=user).update(for_user=hidden_user)
    return HttpResponse('questions forgotten')

@staff_required
@require_http_methods(["POST"])
def unforget_questions(request):
    user = request.user.get_username()
    hidden_user = user + '+hidden'
    PatternAnswer.objects.filter(for_user__exact=hidden_user).update(for_user=user)
    PatternQuestion.objects.filter(for_user__exact=hidden_user).update(for_user=user)
    ParameterAnswer.objects.filter(for_user__exact=hidden_user).update(for_user=user)
    ParameterQuestion.objects.filter(for_user__exact=hidden_user).update(for_user=user)
    return HttpResponse('questions unforgotten')

def _make_score_csv_line(answers):
    parameter_answers = answers['parameters']
    pattern_answer = answers['pattern']
    parameter_scores = []
    parameter_max_scores = []
    total_parameter_score = 0.0
    for answer in parameter_answers:
        parameter_scores.append('{}'.format(answer.score))
        parameter_max_scores.append('{}'.format(answer.max_score))
        total_parameter_score += float(answer.score) / float(answer.max_score)
    pattern_score = ''
    pattern_max_score = ''
    total_pattern_score = 0.0
    if pattern_answer != None:
        pattern_score = '{}'.format(pattern_answer.score)
        pattern_max_score = '{}'.format(pattern_answer.max_score)
        total_pattern_score += float(pattern_answer.score) / float(pattern_answer.max_score)
    score = (
                total_parameter_score / NEEDED_PARAMETER_PERFECT +
                total_pattern_score
            ) / 2.0 * 10.0
    if total_parameter_score > 2:
        score = max(5.0, score)
    score = '{:.1f}'.format(score)
    result = {
        'pattern score': pattern_score,
        'pattern max score': pattern_max_score,
        'overall score': score,
        'overall max score': 10.0,
    }
    for i, (parameter_score, parameter_max_score) in enumerate(zip(parameter_scores, parameter_max_scores)):
        result['parameter score {}'.format(i+1)] = parameter_score
        result['parameter max score {}'.format(i+1)] = parameter_max_score
    return result

def make_score_csv(out_fh, due_datetime, override_due_datetime):
    fields = ['user']
    for i in range(NEEDED_PARAMETER_PERFECT):
        fields.append('parameter score {}'.format(i+1))
        fields.append('parameter max score {}'.format(i+1))
    fields.append('pattern score')
    fields.append('pattern max score')
    fields.append('overall score')
    fields.append('overall max score')
    writer = csv.DictWriter(out_fh, fields)
    writer.writeheader()
    for user in map(lambda x: x.get_username(), User.objects.all()):
        cur_due = override_due_datetime.get(user, due_datetime)
        answers = extract_best_for_user(user, cur_due, NEEDED_PARAMETER_PERFECT)
        for_csv = _make_score_csv_line(answers)
        for_csv['user'] = user
        writer.writerow(for_csv)

@staff_required
def get_scores_csv(request):
    due_datetime = datetime.datetime.strptime(request.GET.get('due'), '%Y-%m-%dT%H:%M%z')
    response = HttpResponse(content_type='text/csv')
    make_score_csv(response, due_datetime, {})
