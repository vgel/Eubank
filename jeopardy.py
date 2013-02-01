#!/usr/bin/env python
import nltk
import requests
from bs4 import BeautifulSoup
import re
import collections
import itertools

most_important = ['NN', 'NNP', 'NNS', 'NNPS', 'CD', 'FW']
allow_important = most_important + ['JJ', 'IN']  # IN = preposition, since nltk has problems tagging things as IN (eg graphite). the common_words filter should keep out actual prepositions
common_english = open('common-english-words').read().split()


class Phrase(object):
    def __init__(self, parent, sentence):
        self.parent = parent
        self.words = self.tokenize(sentence)
        self._bare_words = None

    def tokenize(self, sentence):
        toks = sentence
        if isinstance(sentence, basestring):
            toks = nltk.pos_tag(nltk.word_tokenize(sentence))  # do the inital pre-processing with nltk, but it has problems we need to fix.
        #problems:
        #   Contractions (eg don't) get split into do and n't. We stick those back together.
        #   Embedded phrases get split into `` PHRASE ''. We'll turn those into child Phrase instances instead.
        token_generator = itertools.chain(toks, itertools.repeat(None))  # toks, EOF
        fixed_toks = []
        while True:
            tok = token_generator.next()
            if tok is None:
                break
            elif tok[0] == '``':
                phrase = []
                while True:
                    tok1 = token_generator.next()
                    if tok1 is None:
                        break
                    elif tok1[0] == '\'\'':
                        fixed_toks.append(Phrase(self, phrase))
                        break
                    phrase.append(tok1)
            elif '\'' in tok[0]:
                fixed_toks[-1] = (fixed_toks[-1][0] + tok[0], fixed_toks[-1][1])  # contraction
            else:
                fixed_toks.append(tok)
        return fixed_toks

    def escape(self):
        s = ''
        for x in self.bare_words():
            if type(x) is Phrase:
                s += '"' + x.escape() + '"+'
            else:
                s += x + '+'
        return s[0:-1]

    def bare_words(self):
        if not self._bare_words:
            self._bare_words = map(lambda t: t if type(t) is Phrase else t[0], self.words)
        return self._bare_words

    def __str__(self):
        return 'PHRASE = (' + ', '.join(map(str, self.words)) + ')'

    def __repr__(self):
        return self.__str__()


def phrasify(sentence):
    return Phrase(None, sentence)


def important_words(question):
    p = filter(lambda word: type(word) is Phrase or word[1] in allow_important, phrasify(question).words)
    return map(lambda t: t if type(t) is Phrase else t[0], p)

def is_likely_url(word):
    for x in ['.com', '.net', '.org', '.gov', '.mil']:
        if word.endswith(x):
            return x
    return None


def make_google_url(question):
    s = ''
    for w in question:
        if type(w) is Phrase:
            s += '"' + w.escape() + '"+'
        else:
            tld = is_likely_url(w) #get rid of tlds because it's all spammy SEO/whois services
            if tld:
                s += w[:-len(tld)] + '+'
            else:
                s += w + '+'
    print 'search =', s
    return 'http://www.google.com/search?q=' + s

def normalize(word):
    return re.sub('[^a-z0-9]', '', word.lower())

def is_same_word(word1, word2, first_try=True):
    if normalize(word1) == normalize(word2):
        return True
    if word1[-1] == 's' and normalize(word1[:-1]) == normalize(word2):  # plurals and 's
        return True
    if normalize(word1).startswith(normalize(word2)): #jews == jewish
        return True
    #if '\'' in word1 and nltk.word_tokenize(normalize(word1))[0] == normalize(word2):  # contractions don't == do
    #    return True
    if first_try:
        return is_same_word(word2, word1, False)
    return False


def remove_from_count(x, cnt):
    if type(x) is Phrase:
        for x1 in x.bare_words():
            remove_from_count(x1, cnt)
    elif type(x) is list:
        for x1 in x:
            remove_from_count(x1, cnt)
    else:
        for key in cnt.keys():
            if is_same_word(x, key) and x not in common_english:
                cnt.pop(key)
    return cnt


def blob_google(html, question):
    sts = map(lambda span: span.get_text(), html.find_all('span', 'st'))
    sts_blob = re.sub('[^\sa-zA-Z0-9]', '', ' '.join(sts))
    cnt = collections.Counter(sts_blob.split())
    for x in common_english:
        if x in cnt:
            cnt.pop(x)
    remove_from_count(question.bare_words(), cnt)
    for x in cnt.keys():
        if nltk.pos_tag([x])[0][1] not in allow_important:
            cnt.pop(x)
    print cnt
    return cnt, re.sub('\s+', ' ', sts_blob)


def find_all_single(element, li):
    return [i for i, x in enumerate(li) if x == element]

def find_related_words(dr, key, blob):
    #blob = blob.split()
    blob = phrasify(blob)
    positions = sorted(find_all_single(key, blob.bare_words()))

    i = 0

    def slice_blob(pos):
        if dr < 0:
            return tuple(blob.bare_words()[pos - i:pos])
        else:
            return tuple(blob.bare_words()[pos + 1:pos + i])
    possible = []
    while True:
        cnt = collections.Counter(map(slice_blob, positions))
        if (positions[0] - i >= 0 if dr < 0 else positions[-1] + i <= len(blob.bare_words())) and cnt.most_common()[0][1] / float(sum(cnt.values())) > .3:  # stop at some point...
            print i, cnt.most_common()[0][1] / float(sum(cnt.values())), len(blob.bare_words())
            possible.extend(map(slice_blob, positions))
            i += 1  # try more words
        else:
            i -= 1  # current i didn't meet threshold, decrement it
            possible.extend(map(slice_blob, positions))
            print possible
            possible = filter(lambda t: len(t) > 0, possible)
            if len(possible) == 0:
                return []
            cnt = collections.Counter(possible)

            total = float(sum(cnt.values()))
            def score(key):
                return cnt[key] / total / (1 + 0.05 * len(key))  #start out with frequency, decrement for length (since answers are rarely long)
            return list(sorted(possible, key=score)[-1]) #sort by score, return one with greatest score

def find_key_word(cnt):
    if len(cnt) == 0:
        return None
    total = float(sum(cnt.values()))
    def score(key):
        score = cnt[key] / total
        if nltk.pos_tag([key]) not in most_important:
            score *= 0.9 #disfavor non-nouns
        score *= (1 + 0.01 * len(key)) #slightly favor longer words
        return score
    return sorted(cnt.keys(), key=score)[-1]


def google_it(question):
    html = BeautifulSoup(requests.get(make_google_url(important_words(question))).text)
    cnt, blob = blob_google(html, phrasify(question))
    print blob
    if len(cnt) == 0:
        raise Exception('Couldn\'t understand your sentence (blame nltk)')
    #key_word = cnt.most_common()[0][0]
    key_word = find_key_word(cnt)
    before = find_related_words(-1, key_word, blob)
    after = find_related_words(1, key_word, blob)
    return 'what is ' + (' '.join(before) + ' ' + key_word + ' ' + ' '.join(after)).strip() + '?'

while True:
    print 'que?>',
    try:
        print google_it(raw_input())
    except EOFError:
        break
    except:
        import traceback
        traceback.print_exc()
