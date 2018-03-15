from django.db import models
import bisect
import itertools
import json
import logging
import math
import random
import uuid

logger = logging.getLogger('cachelabweb')

class CacheAccess():
    def __init__(self, data, default_size=1):
        self.type = data['type']  # read or write
        self.address = data['address']
        self.size = data.get('size', default_size)
        self.kind = data.get('kind', None)

    @property
    def address_hex(self):
        return hex(self.address)

    def as_dump(self):
        return {
            'type': self.type,
            'address': self.address,
            'size': self.size,
            'kind': self.kind,
        }


class CacheEntry():
    def __init__(self, data):
        self.valid = data['valid']
        self.lru = data['lru']
        if self.valid:
            self.tag = data['tag']
            self.dirty = data['dirty']
        else:
            self.tag = self.dirty = None

    def as_dump(self):
        return {
            'valid': self.valid,
            'tag': self.tag,
            'lru': self.lru,
            'dirty': self.dirty
        }

    def __repr__(self):
        return 'CacheEntry(%s)' % (self.as_dump())

class CacheParameters(models.Model):
    num_ways = models.IntegerField(default=2)
    num_indices = models.IntegerField(default=4)
    entry_size = models.IntegerField(default=8)
    # FIXME: is_writeback support

    @property
    def offset_bits(self):
        return int(math.log2(self.entry_size))
    
    @property
    def index_bits(self):
        return int(math.log2(self.num_indices))

    @property
    def cache_size_bytes(self):
        return self.num_ways * self.num_indices * self.entry_size

    def split_address(self, address):
        offset = address & ~((~0) << self.offset_bits)
        index = (address >> self.offset_bits) & ~((~0) << self.index_bits)
        tag = (address >> (self.offset_bits + self.index_bits))
        return (tag, index, offset)

    def unsplit_address(self, tag, index, offset):
        return (
            (tag << (self.offset_bits + self.index_bits)) |
            (index << self.offset_bits) |
            offset
        )

    def drop_offset(self, address):
        return address & ((~0) << self.offset_bits)
    
def _update_lru(entry_list, new_most_recent):
    new_most_recent.lru = len(entry_list)
    entry_list.sort(key=lambda e: e.lru)
    for i, e in enumerate(entry_list):
        e.lru = i

def _get_lru(entry_list):
    logger.debug('entry_list = %s', entry_list)
    return list(filter(lambda e: e.lru == 0, entry_list))[0]

class CacheState():
    def __init__(self, params):
        self.params = params
        entries = []
        for index in range(params.num_indices):
            entries.append([])
            for way in range(params.num_ways):
                entries[-1].append(
                    CacheEntry({
                        'valid': False,
                        'tag': None,
                        'lru': way,
                        'dirty': False
                    })
                )
        self.entries = entries

    def to_entries(self):
        return self.entries
    
    def apply_access(self, access, dry_run=False):
        (tag, index, offset) = self.params.split_address(access.address)
        logger.debug('apply_access(%x,%x,%x)', tag, index, offset)
        found = None
        entries_at_index = self.entries[index]
        was_hit = False
        for possible in entries_at_index:
            if possible.tag == tag:
                found = possible
                was_hit = True
                break
        evicted = None
        if found == None:
            # FIXME: record dirty flush here
            found = _get_lru(entries_at_index)
            if found.valid:
                logger.debug('evicted %x', found.tag)
                evicted = self.params.unsplit_address(found.tag, index, 0)
            else:
                logger.debug('no eviction')
            if not dry_run:
                found.valid = True
                found.tag = tag
        # FIXME: conditional on is_writeback?
        if access.type == 'W':
            found.dirty = True
        if not dry_run:
            _update_lru(entries_at_index, found)
        return {
            'hit': was_hit,
            'tag': tag,
            'index': index,
            'offset': offset,
            'evicted': evicted,
        }

    def to_json(self):
        return json.dumps(list(
            map(lambda row: list(map(lambda x: x.as_dump(), row)),
                self.entries)
        ))

    @staticmethod
    def from_json(params, the_json):
        raw_data = json.loads(the_json)
        result = []
        for raw_row in raw_data:
            row = []
            for raw_entry in raw_row:
                row.append(CacheEntry(raw_entry))
            result.append(row)
        state = CacheState(params)
        state.entries = result

# because random.choices isn't available until Python 3.6
def _random_weighted(possibilities, weights):
    cumulative_weights = list(itertools.accumulate(weights))
    weight_index = random.random() * cumulative_weights[-1]
    index = bisect.bisect_left(cumulative_weights, weight_index)
    return possibilities[index]

class CachePattern(models.Model):
    pattern_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parameters = models.ForeignKey('CacheParameters', on_delete=models.PROTECT)
    access_size = models.IntegerField(default=2)
    address_bits = models.IntegerField(default=8)
    # JSON list of cache accesses
    accesses_raw = models.TextField()
    _have_access_results = False

    @property
    def accesses(self):
        return list(map(CacheAccess, json.loads(self.accesses_raw)))

    @property
    def access_results(self):
        self.generate_results()
        return self._access_results
    
    @property
    def final_state(self):
        self.generate_results()
        return self._final_state

    def generate_results(self):
        if not self._have_access_results:
            state = CacheState(self.parameters)
            results = []
            for access in self.accesses:
                results.append(state.apply_access(access))
            self._access_results = results
            self._final_state = state
            self._have_access_results = True

    @staticmethod
    def generate_random(parameters,
            num_accesses=13,
            start_actions = ['normal_miss', 'hit', 'setup_conflict_aggressive', 'setup_conflict_aggressive', 'conflict_miss'],
            access_size=2,
            address_size=8,
            chance_setup_conflict_aggressive=2,
            chance_setup_conflict=1,
            chance_conflict_miss=3,
            chance_hit=3,
            chance_normal_miss=1):
        MAX_TRIES = 20
        result = CachePattern()
        result.access_size = 2
        result.address_size = address_size
        result.parameters = parameters
        accesses =  []
        state = CacheState(parameters)
        would_hit = set()
        would_miss = set()
        used_indices = set()
        used_by_count = {}
        tag_bits = result.address_bits - (parameters.offset_bits + parameters.index_bits)
        offset_bits = parameters.offset_bits
        for i in range(num_accesses):
            if i < len(start_actions):
                access_kind = start_actions[i]
            else:
                possible = ['normal_miss']
                possible_weights = [chance_normal_miss]
                if len(would_hit) > 0:
                    possible.append('hit')
                    possible_weights.append(chance_hit)
                    possible.append('setup_conflict_aggressive')
                    possible_weights.append(chance_setup_conflict_aggressive)
                    possible.append('setup_conflict')
                    possible_weights.append(chance_setup_conflict)
                if len(would_miss) > 0:
                    possible.append('conflict_miss')
                    possible_weights.append(chance_conflict_miss)
                access_kind = _random_weighted(possible, possible_weights)
            if access_kind == 'normal_miss':
                for _ in range(MAX_TRIES):
                    address = random.randrange(0, 1 << result.address_bits)
                    address &= ~(result.access_size - 1)
                    (_, index, _) = parameters.split_address(address)
                    if not address in used_indices:
                        break
            elif access_kind == 'hit':
                address = random.choice(list(would_hit))
            elif access_kind == 'setup_conflict_aggressive':
                best_count = None
                for v in used_by_count.values():
                    if best_count == None:
                        best_count = v
                    elif v > best_count or (v > 0 and best_count == parameters.num_ways):
                        best_count = v
                candidates = []
                for k, v in used_by_count.items():
                    if v == best_count:
                        candidates.append(v)
                base_address = random.choice(candidates)
                (_, index, _) = parameters.split_address(address)
                for _ in range(MAX_TRIES):
                    new_tag = random.randrange(0, 1 << tag_bits)
                    address = parameters.unsplit_address(new_tag, index, 0)
                    if not (address in would_hit or address in would_miss):
                        break
            elif access_kind == 'setup_conflict':
                base_address = random.choice(list(would_hit))
                (_, index, _) = parameters.split_address(address)
                for _ in range(MAX_TRIES):
                    new_tag = random.randrange(0, 1 << tag_bits)
                    address = parameters.unsplit_address(new_tag, index, 0)
                    if not (address in would_hit or address in would_miss):
                        break
            elif access_kind == 'conflict_miss':
                address = random.choice(list(would_miss))
            else:
                assert(False)
            without_offset = parameters.drop_offset(address)
            (_, index, _) = parameters.split_address(address)
            new_offset = random.randrange(0, 1 << offset_bits) & ~(result.access_size - 1)
            address = without_offset | new_offset
            accesses.append(CacheAccess({'type':'R', 'address':address, 'size':result.access_size, 'kind': access_kind}))
            access_result = state.apply_access(accesses[-1])
            used_indices.add(index)
            if index in used_by_count:
                used_by_count[index] = max(used_by_count[index] + 1, parameters.num_ways)
            else:
                used_by_count[index] = 1
            would_hit.add(without_offset)
            would_miss.discard(without_offset)
            if access_result['evicted'] != None:
                would_miss.add(access_result['evicted'])
                would_hit.discard(access_result['evicted'])
        result.accesses_raw = json.dumps(list(map(lambda a: a.as_dump(), accesses)))
        result.generate_results()
        result.save()
        return result

    # FIXME: function to create

class PatternQuestion(models.Model):
    question_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pattern = models.ForeignKey('CachePattern', on_delete=models.PROTECT)
    for_user = models.TextField()
    ask_evict = models.BooleanField(default=True)
    index = models.IntegerField()
    give_first = models.IntegerField(default=5)

    @property
    def tag_bits(self):
        return self.pattern.address_bits - self.pattern.parameters.index_bits - self.pattern.parameters.offset_bits

    @property
    def offset_bits(self):
        return self.pattern.parameters.offset_bits

    @property
    def index_bits(self):
        return self.pattern.parameters.index_bits

    @property
    def address_bits(self):
        return self.pattern.address_bits

    @staticmethod
    def last_question_for_user(for_user):
        return PatternQuestion.objects.filter(for_user__exact=for_user).order_by('-index').first()    

    @staticmethod
    def generate_random(parameters, for_user):
        last_question = PatternQuestion.last_question_for_user(for_user)
        if last_question:
            index = last_question.index + 1
        else:
            index = 0
        pattern = CachePattern.generate_random(parameters)
        result = PatternQuestion()
        result.pattern = pattern
        result.for_user = for_user
        result.index = index
        result.save()
        return result

class PatternAnswer(models.Model):
    question = models.ForeignKey('PatternQuestion', on_delete=models.PROTECT)
    access_results_raw = models.TextField()
    final_state_raw = models.TextField()
    score = models.IntegerField()
    max_score = models.IntegerField()
    was_complete = models.BooleanField(default=False)
    submit_time = models.DateTimeField(auto_now=True,editable=False)
    for_user = models.TextField()

    _access_results = None

    def get_access_results(self):
        if self._access_results != None:
            self._access_results = json.loads(self.access_results_raw)
        return self._access_results 
        

    def set_access_results(self, value):
        self._access_results = _score_answer(value)
        self.access_results_raw = json.dumps(self._access_results)

    access_results = property(get_access_results, set_access_results)

    def _score_answer(self, submitted_results):
        expected_results = question.pattern.access_results
        score = 0
        max_score = 0
        i = 0
        for submitted, expected in zip(submitted_results, expected_results):
            if i >= question.give_first:
                max_score += 4
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
        self.score = score
        self.max_score = max_score
        return submitted_results

    @staticmethod
    def last_for_question(question):
        return PatternAnswer.objects.filter(question=question).order_by('-submit_time').first()

    @staticmethod
    def best_complete_for_user(user):
        return PatternAnswer.objects.filter(for_user=user,was_complete=True).order_by('-score').first()

    @staticmethod
    def num_complete_for_user(user):
        return PatternAnswer.objects.filter(for_user=user,was_complete=True).count()

    @staticmethod
    def last_for_user(user):
        return PatternAnswer.objects.filter(for_user=user).order_by('-submit_time').first()

    @property
    def max_score(self):
        return len(self.access_results) * 4
