#!/usr/bin/env python

from bs4 import BeautifulSoup
import collections
import itertools
import json
import nltk
import re
import requests
import sys

import utils

DEBUG = True

most_important = ['NN', 'NNP', 'NNS', 'NNPS', 'CD', 'FW']
allow_important = most_important + ['JJ', 'IN']
    # IN = preposition, since nltk has problems tagging things as IN (eg
    # graphite). the common_words filter should keep out actual prepositions
common_english = open('common-english-words').read().split()
word_net_lm = nltk.stem.wordnet.WordNetLemmatizer()


class Phrase(object):
    def __init__(self, sentence):
        self.words = self.tokenize(sentence)

    def tokenize(self, sentence):
        toks = sentence
        if isinstance(sentence, basestring):
            toks = nltk.pos_tag(nltk.word_tokenize(sentence))  # do the inital pre-processing with nltk, but it has problems we need to fix.
        # problems:
        #   Contractions (eg don't) get split into do and n't. We stick those back together.
        #   Embedded phrases get split into `` PHRASE ''. We'll turn those into child Phrase instances instead.
        #   Phrases using ' don't get counted
        token_generator = itertools.chain(toks, itertools.repeat(None))  # toks, EOF
        return self._tok_phrase(token_generator)

    def _tok_phrase(self, gen):
        fixed_toks = []
        while True:
            tok = gen.next()
            if tok is None or tok[0] == '\'\'':
                break
            elif tok[0] == '``':
               fixed_toks.append(Phrase(self._tok_phrase(gen)))
            elif '\'' in tok[0] and len(fixed_toks) > 0:
                fixed_toks[-1].add_conj(tok[0])  # contraction
            else:
                fixed_toks.append(Word(*tok))
        return fixed_toks

    def escape(self):
        s = ''
        for x in self.words:
            s += x.get_google_form() + '+'
        return s[0:-1]

    def get_google_form(self):
        return '"' + self.escape() + '"'

    def is_important(self):
        return True

    def __str__(self):
        return 'PHRASE = (' + ', '.join(map(str, self.words)) + ')'

    def __repr__(self):
        return self.__str__()


class Word(object):
    def __init__(self, word, tag=None):
        self.original = word
        self.original_conj = word
        self.is_conj = False
        self.normalized = re.sub('[^a-z0-9]', '', word.lower())
        self.lemma = word_net_lm.lemmatize(word.lower())
        if not tag:
            self.tag = nltk.pos_tag([word])[0][1]
        else:
            self.tag = tag

    def add_conj(self, word):  # add a conjugation eg 'do'.add_conj('n\'t')
        self.is_conj = True
        self.original += word

    def get_google_form(self):
        tld = utils.is_likely_url(self.original)
        if tld:
            return self.original[:-len(tld)]
        return self.original

    def is_important(self):
        return self.tag in allow_important

    def remove_from(self, dict_, allow_lemma=False):
        for x in dict_.keys():
            if x == self.original:
                dict_.pop(x)
            elif allow_lemma and (x == self.normalized or x == self.lemma):
                dict_.pop(x)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return 'Word({0}, {1}, {2})'.format(self.original, self.tag, self.lemma)

    def __hash__(self):
        return hash(self.lemma)

    def __eq__(self, other):
        return type(other) == type(self) and hash(other) == hash(self)


def debug(*args):
    if DEBUG:
        print ' '.join(map(str, args))


def important_words(question):
    return filter(lambda word: word.is_important(), Phrase(question).words)


def make_google_url(question):
    s = 'http://www.google.com/search?q='
    for w in question:
        s += w.get_google_form() + '+'
    debug('search =', s)
    return s


def is_same_word(word1, word2):
    if word1.normalized == word2.normalized:
        return True
    elif word1.lemma == word2.lemma:
        return True
    return False


def remove_from_dict(x, cnt):
    if isinstance(x, Phrase):
        for x1 in x.words:
            print 'removing', x1
            remove_from_dict(x1, cnt)
    elif isinstance(x, basestring):
        for x1 in cnt.keys():
            if x1.lemma == x:
                cnt.pop(x1)
    else:
        for key in cnt.keys():
            if is_same_word(x, key):
                cnt.pop(key)
    return cnt


def blob_google(html, question):
    sts = map(lambda span: span.get_text(), html.find_all('span', 'st'))
    sts_blob = Phrase(' '.join(sts))#Phrase(re.sub('[^\sa-zA-Z0-9]', '', ' '.join(sts)))
    cnt = collections.Counter(sts_blob.words)

    for x in common_english:
        remove_from_dict(x, cnt)
    remove_from_dict(question, cnt)
    for x in cnt.keys():
        if x.tag not in allow_important:
            cnt.pop(x)
    debug(cnt)
    return cnt, sts_blob


def possible_related(direction, positions, blob, threshold):
    position = 0
    possible = []
    limit = positions[0] + 1 if direction < 0 else positions[-1] + 1

    def slice_blob(pos):
        if direction < 0:
            return tuple(blob.words[pos - position:pos])
        else:
            return tuple(blob.words[pos + 1:pos + position])

    for x in xrange(limit):
        cnt = collections.Counter(map(slice_blob, positions))
        if cnt.most_common()[0][1] / float(sum(cnt.values())) > threshold:
            possible.extend(map(slice_blob, positions))
            position += 1
        else:
            break
    return filter(lambda t: len(t) > 0, possible)


def find_related_words(dr, key, blob):
    possible = possible_related(dr, sorted(utils.findall_list(key, blob.words)), blob, 0.3)
    if len(possible) == 0:
        return []
    debug('find_related_words', dr, possible)

    cnt = collections.Counter(possible)
    total = float(sum(cnt.values()))

    def score(key):
        return cnt[key] / total / (1 + 0.03 * len(key))  # start out with frequency, decrement for length (since answers are rarely long)
    scores = map(score, cnt.keys())

    debug_keys = sorted(cnt.keys(), key=score)
    debug('frw', sum(scores), zip(
        map(lambda t: ' '.join(map(lambda t1: t1.original, t)), debug_keys),
        map(lambda score: score / sum(scores), scores),
        map(lambda key: cnt[key], debug_keys)
    ))

    if max(map(lambda score: score / sum(scores), scores)) < 0.2:  # if the greatest score normalized less than 20%, it's probably nothing
        debug('frw', 'no high-scoring for', dr)
        return []

    return list(sorted(cnt.keys(), key=score)[-1])


def find_key_word(cnt):
    if len(cnt) == 0:
        return None
    total = float(sum(cnt.values()))

    def score(key):
        score = cnt[key] / total
        if key.tag not in most_important:
            score *= 0.9  # disfavor non-nouns
        score *= (1 + 0.01 * ((len(key.lemma) - 7) ** 2 * -1 + 1))
                  # slightly favor words of length ~7 (use lemma so form-
                  # agnostic)
        return score
    return sorted(cnt.keys(), key=score)[-1]


def google_it(question):
    html = BeautifulSoup(requests.get(make_google_url(important_words(question))).text)
    cnt, blob = blob_google(html, Phrase(question))
    debug('blob=', ' '.join(map(lambda w: w.original, blob.words)))
    if len(cnt) == 0:
        raise Exception('Couldn\'t understand your sentence (blame nltk)')
    # key_word = cnt.most_common()[0][0]
    key_word = find_key_word(cnt)
    before = map(lambda w: w.original, find_related_words(-1, key_word, blob))
    after = map(lambda w: w.original, find_related_words(1, key_word, blob))
    debug('question =', question)
    debug('key =', key_word)
    return 'what is ' + (' '.join(before) + ' ' + key_word.original + ' ' + ' '.join(after)).strip() + '?'


def main(args):
    global DEBUG
    if len(args) == 1:
        # no args - repl
        while True:
            print 'que?>',
            try:
                print google_it(raw_input())
            except EOFError:
                break
            except:
                import traceback
                traceback.print_exc()
    else:
        # test mode
        DEBUG = False
        print 'Loading testfile...'
        tests = filter(bool, open(args[1]).read().split('\n'))

        print len(tests), 'tests'
        for clue, answer in utils.grouper(2, tests):
            clue = clue.split('~!clue')[1]
            answer = answer.split("~!answer")[1]
            try:
                print '----------------------------------------------------------------'
                print 'clue:', clue
                print 'correct:', answer
                print 'eubank:', google_it(clue)
            except KeyboardInterrupt:
                sys.exit(0)
            except:
                import traceback
                traceback.print_exc()


if __name__ == '__main__':
    main(sys.argv)
