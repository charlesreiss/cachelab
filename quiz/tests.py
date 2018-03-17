from django.test import TestCase

from .models import *

import random

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
                    for address_bits in range(offset_bits + index_bits + ways, offset_bits + index_bits + 6):
                        parameters = CacheParameters.get(
                            num_ways=ways,
                            num_sets=1<<index_bits,
                            block_size=1<<offset_bits,
                            address_bits=address_bits,
                        )
                        for trial in range(5):
                            with self.subTest(offset_bits=offset_bits, index_bits=index_bits, ways=ways, trial=trial, address_bits=address_bits):
                                random.seed(trial)
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
                                        self.assertFalse(result['hit'])
                                    elif 'hit' in expect_type:
                                        self.assertTrue(result['hit'])
                                    if expect_type == 'conflict_miss':
                                        self.assertTrue(result['evicted'] != None)
