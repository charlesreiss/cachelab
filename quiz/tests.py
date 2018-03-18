from django.test import Client, TestCase

from .models import *

import random

import logging

logger = logging.getLogger('cachelabweb')

# Create your tests here.
class PatternQuestionTest(TestCase):
    def test_generate_trivial(self):
        parameters = CacheParameters.get(
            num_ways=1,
            num_sets=1,
            block_size=1,
            address_bits=1,
        )
        pattern = PatternQuestion.generate_random(parameters, 'test',
            num_accesses=6,
            start_actions=['random_miss', 'random_miss', 'conflict_miss', 'hit', 'random_miss', 'conflict_miss'],
            )

    def test_generate_parameter_sweep(self):
        for offset_bits in range(0, 4):
            for index_bits in range(0, 4):
                for ways in range(1, 4):
                    for address_bits in range(offset_bits + index_bits + ways + 1, offset_bits + index_bits + 6):
                        parameters = CacheParameters.get(
                            num_ways=ways,
                            num_sets=1<<index_bits,
                            block_size=1<<offset_bits,
                            address_bits=address_bits,
                        )
                        for trial in range(5):
                            with self.subTest(offset_bits=offset_bits, index_bits=index_bits, ways=ways, trial=trial, address_bits=address_bits):
                                random.seed(trial)
                                logger.info("starting a subtest")
                                desired_actions = ['random_miss'] + (['setup_conflict_aggressive'] * (ways)) + ['conflict_miss'] + \
                                                    ['hit', 'random_miss', 'conflict_miss', 'hit', 'hit']
                                question = PatternQuestion.generate_random(parameters, 'test',
                                    num_accesses=len(desired_actions),
                                    start_actions=desired_actions
                                    )
                                accesses = question.pattern.accesses
                                results = question.pattern.access_results
                                for expect_type, result, access in zip(desired_actions, results, accesses):
                                    self.assertEqual(expect_type, access.kind)
                                    if 'miss' in expect_type:
                                        self.assertFalse(result.hit.value)
                                    elif 'hit' in expect_type:
                                        self.assertTrue(result.hit.value)
                                    if expect_type == 'conflict_miss':
                                        self.assertTrue(result.evicted.value != None)

def login_as(client, username):
    from django.contrib.auth.models import User
    try:
        account = User.objects.get(username=username)
    except User.DoesNotExist:
        account = User.objects.create_user(username)
    client.force_login(account) 

class PatternEvaluateTest(TestCase):
    def test_evaluate_simple(self):
        pattern = CachePattern()
        # 4 offset bits, 4 set bits, 8 tag bits
        pattern.parameters = CacheParameters.get(num_ways=3,num_sets=16,block_size=16,address_bits=16)
        pattern.accesses = [
            CacheAccess(0x0123), # miss
            CacheAccess(0x0123), # hit
            CacheAccess(0x0223), # miss
            CacheAccess(0x0323), # miss
            CacheAccess(0x0123), # hit
            CacheAccess(0x0423), # miss, evicting 0x0220
            CacheAccess(0x0523), # miss, evicting 0x0320
        ]
        results = pattern.access_results
        expected_results = [
            CacheAccessResult.from_reference(False, 0x01, 0x2, 0x3, None),
            CacheAccessResult.from_reference(True,  0x01, 0x2, 0x3, None),
            CacheAccessResult.from_reference(False, 0x02, 0x2, 0x3, None),
            CacheAccessResult.from_reference(False, 0x03, 0x2, 0x3, None),
            CacheAccessResult.from_reference(True,  0x01, 0x2, 0x3, None),
            CacheAccessResult.from_reference(False, 0x04, 0x2, 0x3, 0x0220),
            CacheAccessResult.from_reference(False, 0x05, 0x2, 0x3, 0x0320),
        ]
        for expected, actual in zip(expected_results, pattern.access_results):
            self.assertEquals(expected.hit.value, actual.hit.value)
            self.assertEquals(expected.tag.value, actual.tag.value)
            self.assertEquals(expected.index.value, actual.index.value)
            self.assertEquals(expected.offset.value, actual.offset.value)
            self.assertEquals(expected.evicted.value, actual.evicted.value)

class PatternSubmitTest(TestCase):
    def test_evaluate_simple(self):
        pattern = CachePattern()
        # 4 offset bits, 4 set bits, 8 tag bits
        pattern.parameters = CacheParameters.get(num_ways=3,num_sets=16,block_size=16,address_bits=16)
        pattern.accesses = [
            CacheAccess(0x0123), # miss
            CacheAccess(0x0123), # hit
            CacheAccess(0x0223), # miss
            CacheAccess(0x0323), # miss
            CacheAccess(0x0123), # hit
            CacheAccess(0x0423), # miss, evicting 0x0220
            CacheAccess(0x0523), # miss, evicting 0x0320
        ]
        pattern.save()
        #expected_results = [
        #0    CacheAccessResult.from_reference(False, 0x01, 0x2, 0x3, None),
        #1    CacheAccessResult.from_reference(True,  0x01, 0x2, 0x3, None),
        #2    CacheAccessResult.from_reference(False, 0x02, 0x2, 0x3, None),
        #3    CacheAccessResult.from_reference(False, 0x03, 0x2, 0x3, None),
        #4    CacheAccessResult.from_reference(True,  0x01, 0x2, 0x3, None),
        #5    CacheAccessResult.from_reference(False, 0x04, 0x2, 0x3, 0x0220),
        #6    CacheAccessResult.from_reference(False, 0x05, 0x2, 0x3, 0x0320),
        #]
        question = PatternQuestion()
        question.index = 0
        question.pattern = pattern
        question.for_user = 'test'
        question.give_first = 1
        question.save()
        c = Client()
        login_as(c, 'test')
        question_form = c.get('/pattern-question')
        logger.debug('question_form : %s', question_form)
        self.assertEqual(question_form.context['show_correct'], False)
        self.assertEqual(question_form.context['show_invalid'], False)
        self.assertEqual(question_form.context['accesses_with_default_and_correct_and_given'][0],
            (CacheAccess(0x0123),
             CacheAccessResult.from_reference(False, 0x01, 0x2, 0x3, None, tag_bits=8),
             CacheAccessResult.from_reference(False, 0x01, 0x2, 0x3, None, tag_bits=8),
             True)
        )
        self.assertEqual(question_form.context['accesses_with_default_and_correct_and_given'][-1],
            (CacheAccess(0x0523),
             CacheAccessResult.empty(),
             CacheAccessResult.from_reference(False, 0x05, 0x2, 0x3, 0x320, tag_bits=8, address_bits=16),
             False)
        )
        response = c.post('/submit-pattern-answer/{}'.format(question.question_id), {
            'access_hit_1':    'hit',
            'access_tag_1':    '0x1',
            'access_index_1':  '0x2',
            'access_offset_1': '0x3',

            'access_hit_2':    'miss-noevict',
            'access_tag_2':    '0x2',
            'access_index_2':  '0x2',
            'access_offset_2': '0x3',

            'access_hit_3':    'miss-noevict',
            'access_tag_3':    '0x3',
            'access_index_3':  '0x2',
            'access_offset_3': '0x3',

            'access_hit_4':    'hit',
            'access_tag_4':    '0x1',
            'access_index_4':  '0x2',
            'access_offset_4': '0x3',

            'access_hit_5':    'miss-evict',
            'access_tag_5':    '0x4',
            'access_index_5':  '0x2',
            'access_offset_5': '0x3',
            'access_evicted_5':  '220',

            'access_hit_6':    'miss-evict',
            'access_tag_6':    '0x5',
            'access_index_6':  '0x2',
            'access_offset_6': '0x3',
            'access_evicted_6':  '0x0000000000000320',
        })
        logger.debug('POST response was %s', response)
        self.assertTrue(response.status_code >= 300 and response.status_code < 400)
        last_answer = PatternAnswer.last_for_question_and_user(question, 'test')
        self.assertTrue(last_answer.was_complete)
        self.assertFalse(last_answer.was_save)
        self.assertEqual(last_answer.score, 6 * 5)
        self.assertEqual(last_answer.max_score, 6 * 5)



class ParameterSubmitTest(TestCase):
    def test_evaluate_simple(self):
        param_target = CacheParameters.get(
            num_ways=7,
            num_sets=128, # 7 index bits
            block_size=256, # 8 offset bits
            address_bits=16 # --> 1 tag bit
        )
        question = ParameterQuestion()
        question.parameters = param_target
        question.index = 0
        question.missing_parts = ['tag_bits', 'offset_bits', 'cache_size_bytes', 'num_sets', 'set_size_bytes', 'way_size_bytes']
        question.given_parts = ['num_ways', 'index_bits', 'block_size', 'address_bits']
        question.for_user = 'test'
        question.save()
        
        c = Client()
        login_as(c, 'test')
        question_form = c.get('/parameter-question')
        logger.debug('question_form : %s', question_form)
        self.assertEqual(question_form.context['show_correct'], False)
        self.assertEqual(question_form.context['mark_invalid'], False)
        self.assertEqual(question_form.context['params'], [
            {'id': 'tag_bits', 'name': 'tag bits', 'value': ResultItem.empty_invalid(), 'correct_value': '1', 'given': False},
            {'id': 'index_bits', 'name': 'index bits', 'value': ResultItem(string='7',value=7,correct=True,invalid=False), 'correct_value': '7', 'given': True},
            {'id': 'offset_bits', 'name': 'offset bits', 'value': ResultItem.empty_invalid(), 'correct_value': '8', 'given': False},
            {'id': 'cache_size_bytes', 'name': 'cache size (bytes)', 'value': ResultItem.empty_invalid(), 'correct_value': '224K','given': False},
            {'id': 'num_sets', 'name': 'number of sets', 'value': ResultItem.empty_invalid(), 'correct_value': '128', 'given': False},
            {'id': 'num_ways', 'name': 'number of ways', 'value': ResultItem(string='7',value=7,correct=True,invalid=False), 'correct_value': '7', 'given': True},
            {'id': 'block_size', 'name': 'block size (bytes)', 'value': ResultItem(string='256',value=256,correct=True,invalid=False), 'correct_value': '256', 'given': True},
            {'id': 'set_size_bytes', 'name': 'total bytes per set', 'value': ResultItem.empty_invalid(), 'correct_value': '1792','given': False},
            {'id': 'way_size_bytes', 'name': 'total bytes per way', 'value': ResultItem.empty_invalid(), 'correct_value': '32K', 'given': False},
            {'id': 'address_bits', 'name': 'address bits', 'value': ResultItem(string='16',value=16,correct=True,invalid=False), 'correct_value': '16','given': True},
        ])
        response = c.post('/submit-parameter-answer/{}'.format(question.question_id), {
            'tag_bits': '  1  ',
            'offset_bits': '8',
            'cache_size_bytes': '    224 K',
            'num_sets': '128',
            'set_size_bytes': '1.75K',
            'way_size_bytes': '32769',
        })
        logger.debug('POST response was %s', response)
        self.assertTrue(response.status_code >= 300 and response.status_code < 400)
        last_answer = ParameterAnswer.last_for_question_and_user(question, 'test')
        logger.debug('last_answer answers %s', last_answer.answer)
        self.assertTrue(last_answer.was_complete)
        self.assertFalse(last_answer.was_save)
        self.assertEqual(last_answer.score, 5)
        self.assertEqual(last_answer.max_score, 6)


