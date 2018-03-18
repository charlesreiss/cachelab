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
    def __init__(self, address, size=1, kind=None, type='R'):
        self.address = address
        self.size = size
        self.kind = kind

    @property
    def address_hex(self):
        return hex(self.address)

    @property
    def is_write(self):
        return False

    @property
    def is_read(self):
        return True

    def as_dump(self):
        return {
            'address': self.address,
            'size': self.size,
            'kind': self.kind,
        }

    def __repr__(self):
        return 'CacheAccess[0x{:x},kind={},size={}]'.format(self.address, self.kind, self.size)

    def __eq__(self, other):
        return self.address == other.address and self.size == other.size

def format_hex(value, bits=None):
    if value == None:
        return ''
    elif bits != None:
        width = int((bits + 3) / 4)
        return '0x{:0{width}x}'.format(value, width=width)
    else:
        return '0x{:x}'.format(value)

class ResultItem():
    def __init__(self, value, string=None, invalid=False, correct=True):
        self.value = value
        self.string = string
        self.invalid = invalid
        self.correct = correct

    @staticmethod
    def empty_invalid():
        return ResultItem(None, string='', invalid=True, correct=False)

    def __repr__(self):
        return '{} ({},invalid={},correct={})'.format(
            str(self.string),
            hex(self.value) if self.value != None else '(none)',
            str(self.invalid),
            str(self.correct),
        )

    def __eq__(self, other):
        return (
            self.string == other.string and
            self.value == other.value and
            self.invalid == other.invalid and
            self.correct == other.correct
        )

class CacheAccessResult():
    @staticmethod
    def from_reference(hit, tag, index, offset, evicted, tag_bits=None, index_bits=None, offset_bits=None, address_bits=None):
        self = CacheAccessResult()
        self.hit = ResultItem(value=hit)
        self.tag = ResultItem(value=tag, string=format_hex(tag, tag_bits))
        self.index = ResultItem(value=index, string=format_hex(index, index_bits))
        self.offset = ResultItem(value=offset, string=format_hex(offset, offset_bits))
        self.evicted = ResultItem(value=evicted, string=format_hex(evicted, address_bits))
        return self

    @staticmethod
    def empty():
        self = CacheAccessResult()
        self.hit = ResultItem(None, string='', invalid=True)
        self.tag = ResultItem(None, string='', invalid=True)
        self.index = ResultItem(None, string='', invalid=True)
        self.offset = ResultItem(None, string='', invalid=True)
        self.evicted = ResultItem(None, string='', invalid=True)
        return self

    def set_from_string(self, key, value):
        int_value = value_from_hex(value)
        self.__dict__[key] = ResultItem(
            value=int_value,
            string=value,
            invalid=int_value==None,
            correct=None
        )
        return int_value != None

    def set_bool(self, key, value):
        self.__dict__[key] = ResultItem(
            value=value,
            invalid=False,
            correct=None
        )

    def set_invalid(self, key):
        self.__dict__[key] = ResultItem(
            value=None,
            invalid=True,
            correct=None
        )

    def as_dump_reference(self):
        return {
            'hit': self.hit.value,
            'tag': self.tag.value,
            'index': self.index.value,
            'offset': self.offset.value,
            'evicted': self.evicted.value
        }
    
    def as_dump(self):
        return {
            'hit': vars(self.hit),
            'tag': vars(self.tag),
            'index': vars(self.index),
            'offset': vars(self.offset),
            'evicted': vars(self.evicted),
        }

    def __repr__(self):
        return 'CacheAccessResult[hit={},tag={},index={},offset={},evicted={}]'.format(
            repr(self.hit),
            repr(self.tag),
            repr(self.index),
            repr(self.offset),
            repr(self.evicted),
        )

    def __eq__(self, other):
        return (
            self.hit == other.hit and
            self.tag == other.tag and
            self.index == other.index and
            self.offset == other.offset and
            self.evicted == other.evicted
        )

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
    num_sets = models.IntegerField(default=4)
    block_size = models.IntegerField(default=8)
    address_bits = models.IntegerField(default=8)
    # FIXME: is_writeback support

    @property
    def offset_bits(self):
        return int(math.log2(self.block_size))
    
    @property
    def index_bits(self):
        return int(math.log2(self.num_sets))

    @property
    def tag_bits(self):
        return self.address_bits - self.offset_bits - self.index_bits

    @property
    def set_size_bytes(self):
        return self.num_ways * self.block_size

    @property
    def way_size_bytes(self):
        return self.num_sets * self.block_size

    @property
    def cache_size_bytes(self):
        return self.num_ways * self.num_sets * self.block_size

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


    @staticmethod
    def get(num_ways, num_sets, block_size, address_bits):
        possible = CacheParameters.objects.filter(
            num_ways=num_ways,
            num_sets=num_sets,
            block_size=block_size,
            address_bits=address_bits,
        )
        if len(possible) == 0:
            result = CacheParameters()
            result.num_ways = num_ways
            result.num_sets = num_sets
            result.block_size = block_size
            result.address_bits = address_bits
            result.save()
            return result
        else:
            return possible[0]

    @staticmethod
    def random(
            min_ways=1, max_ways=32, min_sets_log=0,
            max_sets_log=24, min_block_size_log=0,
            max_block_size_log=10,
            min_address_bits=8,
            max_address_bits=64,
            address_bits_rounding=8,
            min_tag_bits=1,
            max_cache_size=128 * 1024 * 1024):
        while True:
            num_ways = random.randint(min_ways, max_ways)
            way_bits = int(math.log2(num_ways)) + 1
            index_bits = random.randint(min_sets_log, max_sets_log)
            num_sets = 1 << index_bits
            offset_bits = random.randint(min_block_size_log, max_block_size_log)
            block_size = 1 << offset_bits
            min_tag_bits = max(min_tag_bits, way_bits)
            min_address_bits = max(min_address_bits, index_bits + offset_bits + min_tag_bits)
            address_bits = random.randint(min_address_bits, max_address_bits)
            if address_bits % address_bits_rounding > 0:
                address_bits += address_bits_rounding - (address_bits % address_bits_rounding)
            cache_size = num_ways * block_size * num_sets
            if cache_size < max_cache_size:
                break
        return CacheParameters.get(num_ways=num_ways, num_sets=num_sets, block_size=block_size, address_bits=address_bits)



all_cache_question_parameters = [
    'tag_bits',
    'index_bits',
    'offset_bits',
    'cache_size_bytes',
    'num_sets',
    'num_ways',
    'block_size',
    'set_size_bytes',
    'way_size_bytes',
    'address_bits',
]

def _can_find_parameters_from(given_parts):
    known_parts = given_parts
    done = False
    equations = [
        set(['block_size', 'offset_bits']),
        set(['index_bits', 'num_sets']),
        set(['block_size', 'set_size_bytes', 'num_ways']),
        set(['block_size', 'num_ways', 'num_sets', 'cache_size_bytes']),
        set(['tag_bits', 'index_bits', 'offset_bits', 'address_bits']),
    ]
    while not done:
        done = True
        for equation in equations:
            if len(known_parts & equation) == len(equation) - 1:
                known_parts |= equation
                done = False
    return len(known_parts) == len(all_cache_question_parameters)

def _all_subsets(lst):
    iters = []
    for i in range(len(lst)):
        iters.append(itertools.combinations(lst, i))
    return map(frozenset, itertools.chain(*iters))

def _get_cache_givens_to_ask():
    possible = set()
    for givens in _all_subsets(all_cache_question_parameters):
        if _can_find_parameters_from(givens):
            possible.add(givens)
    filtered = set()
    for givens in possible:
        can_trim = False
        for item in givens:
            if givens - set([item]) in possible:
                can_trim = True
        if not can_trim:
            filtered.add(givens)
    logger.info('all_cache_given_sets = %s', filtered)
    return list(filtered)

all_cache_given_sets = _get_cache_givens_to_ask()

class ParameterQuestion(models.Model):
    question_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    for_user = models.TextField()
    parameters = models.ForeignKey('CacheParameters', on_delete=models.PROTECT)
    missing_parts_raw = models.TextField()
    given_parts_raw = models.TextField()
    index = models.IntegerField()

    def get_missing_parts(self):
        return json.loads(self.missing_parts_raw)
    
    def set_missing_parts(self, missing_parts):
        self.missing_parts_raw = json.dumps(missing_parts)

    missing_parts = property(get_missing_parts, set_missing_parts)

    def get_given_parts(self):
        return json.loads(self.given_parts_raw)
    
    def set_given_parts(self, given_parts):
        self.given_parts_raw = json.dumps(given_parts)

    given_parts = property(get_given_parts, set_given_parts)

    def find_cache_property(self, name):
        return getattr(self.parameters, name)
   
    @staticmethod
    def generate_new(for_user):
        which_given = list(random.choice(all_cache_given_sets))
        which_parameters = CacheParameters.random()
        q = ParameterQuestion()
        last_question = ParameterQuestion.last_for_user(for_user)
        if last_question != None:
            q.index = last_question.index + 1
        else:
            q.index = 0
        q.for_user = for_user
        q.parameters = which_parameters
        q.given_parts = which_given
        q.missing_parts = list(filter(lambda x: x not in which_given, all_cache_question_parameters))
        q.save()
        return q

    @staticmethod
    def last_for_user(for_user):
        return ParameterQuestion.objects.filter(for_user__exact=for_user).order_by('-index').first()    


class ParameterAnswer(models.Model):
    for_user = models.TextField()
    question = models.ForeignKey('ParameterQuestion', on_delete=models.PROTECT)
    submit_time = models.DateTimeField(auto_now=True,editable=False)
    answer_raw = models.TextField()
    was_complete = models.BooleanField()
    was_save = models.BooleanField()
    score = models.IntegerField()
    score_ratio = models.FloatField()
    _answer = None
    
    class Meta: 
        indexes = [
            models.Index(fields=['for_user', 'submit_time']),
            models.Index(fields=['for_user', 'was_complete', 'score_ratio']),
        ]

    def set_answer_from_post(self, post):
        self._answer = self._post_to_scored_answer(post)
        self.answer_raw = json.dumps({k: vars(v) for k, v in self._answer.items()})
        self.score_ratio = float(self.score) / self.max_score

    def get_answer(self):
        if self._answer == None:
            answer_dict = json.loads(self.answer_raw)
            self._answer = {k: ResultItem(**v) for k, v in answer_dict.items()}
        return self._answer

    answer = property(get_answer)

    @property
    def max_score(self):
        return len(self.question.missing_parts)

    def _post_to_scored_answer(self, answer):
        score = 0
        incomplete = False
        result = {}
        for item in self.question.missing_parts:
            string = answer.get(item, '')
            value = value_from_any(string)
            invalid_p = value == None
            correct_p = value == self.question.find_cache_property(item)
            if invalid_p:
                incomplete = True
            result[item] = ResultItem(
                value=value,
                string=string,
                invalid=invalid_p,
                correct=correct_p
            )
            if correct_p:
                score += 1
        self.score = score
        self.was_complete = not incomplete
        return result

    @staticmethod
    def last_for_question_and_user(question, user):
        if question == None:
            return None
        return ParameterAnswer.objects.filter(question=question, for_user=user).order_by('-submit_time').first()

    @staticmethod
    def last_for_user(user):
        return ParameterAnswer.objects.filter(for_user=username).order_by('-submit_time').first()
    
    @staticmethod
    def num_complete_for_user(user):
        return ParameterAnswer.objects.filter(for_user=user, was_complete=True).count()
    
    @staticmethod
    def best_K_for_user(user, K):
        return ParameterAnswer.objects.filter(for_user=user, was_complete=True).order_by('-score_ratio', '-submit_time')[:K]

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
        for index in range(params.num_sets):
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
        if access.is_write:
            found.dirty = True
        if not dry_run:
            _update_lru(entries_at_index, found)
        return CacheAccessResult.from_reference(
            hit=was_hit,
            tag=tag,
            index=index,
            offset=offset,
            evicted=evicted,
            tag_bits=self.params.tag_bits,
            index_bits=self.params.index_bits,
            offset_bits=self.params.offset_bits,
            address_bits=self.params.address_bits,
        )

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

    def get_accesses(self):
        return list(map(lambda x: CacheAccess(**x), json.loads(self.accesses_raw)))

    def set_accesses(self, accesses):
        self.accesses_raw = json.dumps(list(map(lambda x: x.as_dump(), accesses)))

    accesses = property(get_accesses, set_accesses)

    @property
    def access_results(self):
        self.generate_results()
        return self._access_results

    @property
    def address_bits(self):
        return self.parameters.address_bits
    
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


    """
    Generate a psuedorandom access pattern.
    
    Takes relative frequencies of the types of accesses (on average, chosen randomly) and a fixed pattern
    to start with.

    The access types:
    * random_miss --- a cache miss, by choosing a random address, with fallback to explicitly searching for
        a missing address
    * miss_prefer_empty --- a cache miss, in an empty set if possible
    * miss_prefer_used --- a cache miss, in a used set if possible, with a preference to avoid conflict misses
    * conflict_miss --- a cache miss to a previously evicted block
    * setup_conflict --- a cache miss to an already-accessed set
    * setup_conflict_aggressive --- a cache miss to a most-full already accessed set
    """
    @staticmethod
    def generate_random(parameters,
            num_accesses=14,
            start_actions = ['random_miss', 'hit', 'setup_conflict_aggressive', 'setup_conflict_aggressive', 'setup_conflict_aggressive', 'conflict_miss'],
            access_size=2,
            chance_setup_conflict_aggressive=3,
            chance_setup_conflict=2,
            chance_conflict_miss=5,
            chance_hit=5,
            chance_random_miss=0.5,
            chance_miss_prefer_empty=1,
            chance_miss_prefer_used=0.5):
        MAX_TRIES = 20
        MAX_RANDOM_LIST = 1000
        result = CachePattern()
        result.access_size = 2
        result.parameters = parameters
        accesses =  []
        state = CacheState(parameters)
        would_hit = set()
        would_miss = set()  # miss AND previously accessed
        used_indices = set()
        used_by_count = {}
        tag_bits = parameters.tag_bits
        index_bits = parameters.index_bits
        offset_bits = parameters.offset_bits
        address_bits = parameters.address_bits
        def _find_unused_miss():
            if len(used_indices) != parameters.num_sets:
                possible_indices = []
                for _ in range(MAX_TRIES):
                    index = random.randrange(0, 1 << index_bits)
                    if index not in used_indices:
                        tag = random.randrange(0, 1 << tag_bits)
                        return parameters.unsplit_address(tag, index)
                for index in range(parameters.num_sets):
                    if index in used_indices:
                        continue
                    possible_indices.append(index)
                    if len(possible_indices) > MAX_RANDOM_LIST:
                        break
                index = random.choice(possible_indices)
                tag = random.randrange(0, 1 << tag_bits)
                return parameters.unsplit_address(tag, index, 0)
            else:
                return None

        def _find_miss_for_index(index, prefer_non_conflict=True):
            if prefer_non_conflict:
                # first try to find a random non-conflict miss
                for _ in range(MAX_TRIES):
                    tag = random.randrange(0, 1 << parameters.tag_bits)
                    block_address = parameters.unsplit_address(tag, index, 0)
                    if block_address in would_hit or block_address in would_miss:
                        continue
                    return block_address
            # then try to find a random maybe-conflict-miss
            for _ in range(MAX_TRIES):
                tag = random.randrange(0, 1 << parameters.tag_bits)
                block_address = parameters.unsplit_address(tag, index, 0)
                if block_address in would_hit:
                    continue
                return block_address
            # then search exhaustively for possible blocks
            possible_blocks = []
            for tag in range(0, 1 << parameters.tag_bits):
                block_address = parameters.unsplit_address(tag, index, 0)
                if block_address in would_hit:
                    continue
                possible_blocks.append(block_address)
                if len(possible_blocks) > MAX_RANDOM_LIST:
                    break
            return random.choice(possible_blocks)

        def _find_used_miss():
            if len(used_indices) == 0:
                return random.randrange(0, 1 << address_bits)
            index = random.choice(list(used_indices))
            return _find_miss_for_index(index)

        def _find_random_miss():
            for _ in range(MAX_TRIES):
                address = random.randrange(0, 1 << address_bits)
                address &= ~(result.access_size - 1)
                (tag, index, _) = parameters.split_address(address)
                block_address = parameters.unsplit_address(tag, index, 0)
                if block_address not in would_hit:
                    return block_address
            # fallback to other mechanisms
            address = _find_unused_miss()
            if address == None:
                address = _find_used_miss()
            return address
            
        for i in range(num_accesses):
            if i < len(start_actions):
                access_kind = start_actions[i]
            else:
                possible = ['random_miss']
                possible_weights = [chance_normal_miss]
                possible.append('miss_prefer_empty')
                possible_weights.append(chance_miss_prefer_empty)
                possible.append('miss_prefer_used')
                possible_weights.append(chance_miss_prefer_used)
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
            logger.debug('chosen access kind is %s', access_kind)
            if access_kind == 'random_miss':
                address = _find_random_miss()
            elif access_kind == 'miss_prefer_empty':
                address = _find_unused_miss()
                if address == None:
                    address = _find_random_miss()
            elif access_kind == 'miss_prefer_used':
                address = _find_used_miss()
            elif access_kind == 'hit':
                address = random.choice(list(would_hit))
            elif access_kind == 'conflict_miss':
                address = random.choice(list(would_miss))
            elif access_kind == 'setup_conflict_aggressive':
                best_count = None
                for v in used_by_count.values():
                    if best_count == None:
                        best_count = v
                    elif v > best_count or (v > 0 and best_count == parameters.num_ways):
                        best_count = v
                logger.debug('looking for count %s', best_count)
                candidates = []
                for k, v in used_by_count.items():
                    if v == best_count:
                        candidates.append(k)
                logger.debug('candidates are %s', candidates)
                index = random.choice(candidates)
                address = _find_miss_for_index(index, prefer_non_conflict=False)
            elif access_kind == 'setup_conflict':
                base_address = random.choice(list(would_hit))
                (_, index, _) = parameters.split_address(address)
                address = _find_miss_for_index(index, prefer_non_conflict=False)
            else:
                raise Exception("Could not identify access type")
            assert address != None, 'no address generated for kind {}'.format(access_kind)
            without_offset = parameters.drop_offset(address)
            (tag, index, _) = parameters.split_address(address)
            new_offset = random.randrange(0, 1 << offset_bits) & ~(result.access_size - 1)
            address = without_offset | new_offset
            accesses.append(CacheAccess(address=address, size=result.access_size, kind=access_kind))
            access_result = state.apply_access(accesses[-1])
            (new_tag, new_index, _) = parameters.split_address(address)
            assert tag == new_tag
            assert index == new_index
            used_indices.add(index)
            if index in used_by_count:
                used_by_count[index] = max(used_by_count[index] + 1, parameters.num_ways)
            else:
                used_by_count[index] = 1
            would_hit.add(without_offset)
            would_miss.discard(without_offset)
            if access_result.evicted.value != None:
                would_miss.add(access_result.evicted.value)
                would_hit.discard(access_result.evicted.value)
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
    give_first = models.IntegerField(default=6)
   
    class Meta: 
        indexes = [
            models.Index(fields=['for_user', 'index']),
        ]

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
    def last_for_user(for_user):
        return PatternQuestion.objects.filter(for_user__exact=for_user).order_by('-index').first()    

    @staticmethod
    def generate_random(parameters, for_user, **extra_args):
        last_question = PatternQuestion.last_for_user(for_user)
        if last_question:
            index = last_question.index + 1
        else:
            index = 0
        pattern = CachePattern.generate_random(parameters, **extra_args)
        result = PatternQuestion()
        result.pattern = pattern
        result.for_user = for_user
        result.index = index
        result.save()
        return result

def value_from_hex(x):
    if x != None and (x.startswith('0x') or x.startswith('0X')):
        x = x[2:]
    try:
        return int(x, 16)
    except TypeError:
        return None
    except ValueError:
        return None

sizes = {
        'k': 1024,
        'm': 1024 * 1024,
        'g': 1024 * 1024 * 1024,
        't': 1024 * 1024 * 1024 * 1024,
        }

def value_from_any(x):
    if x == None:
        return None
    x = x.lower().strip()
    if x == '':
        return None
    if x[-1] == 'b':
        x = x[:-1]
    if x == '':
        return None
    if x[-1] in sizes:
        try:
            return int(float(x[:-1].strip()) * sizes[x[-1]])
        except TypeError:
            return None
        except ValueError:
            return None
    try:
        return int(x)
    except TypeError:
        return None
    except ValueError:
        return None

class PatternAnswer(models.Model):
    question = models.ForeignKey('PatternQuestion', on_delete=models.PROTECT)
    access_results_raw = models.TextField()
    final_state_raw = models.TextField()
    score = models.IntegerField()
    max_score = models.IntegerField()
    was_complete = models.BooleanField(default=False)
    was_save = models.BooleanField(default=False)
    submit_time = models.DateTimeField(auto_now=True,editable=False)
    for_user = models.TextField()

    class Meta:
        indexes = [
            models.Index(fields=['for_user', 'submit_time']),
            models.Index(fields=['for_user', 'was_complete', 'score']),
        ]

    _access_results = None

    def get_access_results(self):
        if self._access_results == None:
            self._access_results = json.loads(self.access_results_raw)
        return self._access_results 
        

    def set_access_results(self, value):
        self._access_results = self._score_answer(value)
        self.access_results_raw = json.dumps(list(map(lambda x: x.as_dump(), self._access_results)))

    access_results = property(get_access_results, set_access_results)

    def _score_answer(self, submitted_results):
        expected_results = self.question.pattern.access_results
        score = 0
        max_score = 0
        for i, (submitted, expected) in enumerate(zip(submitted_results, expected_results)):
            if i < self.question.give_first:
                continue
            max_score += 5
            if submitted.hit.value == expected.hit.value:
                score += 1
                submitted.hit.correct = True
            else:
                submitted.hit.correct = False
            for which in ['tag', 'index', 'offset']:
                if getattr(submitted, which).value == getattr(expected, which).value:
                    getattr(submitted, which).correct = True
                    score += 1
                else:
                    getattr(submitted, which).correct = False
            if expected.evicted.value == submitted.evicted.value:
                score += 1
                submitted.evicted.correct = True
        self.score = score
        self.max_score = max_score
        return submitted_results

    @staticmethod
    def last_for_question_and_user(question, for_user):
        if question == None:
            return None
        return PatternAnswer.objects.filter(question=question, for_user=for_user).order_by('-submit_time').first()

    @staticmethod
    def best_complete_for_user(user):
        return PatternAnswer.objects.filter(for_user=user,was_complete=True).order_by('-score').first()

    @staticmethod
    def num_complete_for_user(user):
        return PatternAnswer.objects.filter(for_user=user,was_complete=True).count()

    @staticmethod
    def last_for_user(user):
        return PatternAnswer.objects.filter(for_user=user).order_by('-submit_time').first()
