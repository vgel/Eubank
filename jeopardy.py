#!/usr/bin/env python
import nltk
import requests
from bs4 import BeautifulSoup
import re
import collections
import itertools

allow_important = ['NN', 'NNP', 'NNS', 'NNPS', 'CD', 'FW', 'JJ', 'IN']  # IN = preposition, since nltk has problems tagging things as IN (eg graphite). the common_words filter should keep out actual prepositions
common_english = open('common-english-words').read().split()


class Phrase(object):
    def __init__(self, parent, sentence):
        self.parent = parent
        self.words = self.tokenize(sentence)

    def tokenize(self, sentence):
        toks = sentence
        if type(sentence) == str:
            toks = nltk.pos_tag(nltk.word_tokenize(sentence))  # do the inital pre-processing with nltk, but it has problems we need to fix.
        #print toks
        #problems:
        #   Contractions (eg don't) get split into do and n't. We stick those back together.
        #   Embedded phrases get split into `` PHRASE ''. We'll turn those into child Phrase instances instead.
        token_generator = itertools.chain(
            toks, itertools.repeat(None))  # toks, EOF
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
                fixed_toks[-1] = (fixed_toks[-1][0] + tok[
                                  0], fixed_toks[-1][1])  # contraction
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
        return map(lambda t: t if type(t) is Phrase else t[0], self.words)

    def __str__(self):
        return 'PHRASE = "' + ', '.join(map(str, self.words)) + '"'

    def __repr__(self):
        return self.__str__()


def phrasify(sentence):
    return Phrase(None, sentence)


def important_words(question):
    p = filter(lambda word: type(word) is Phrase or word[1] in allow_important, phrasify(question).words)
    return map(lambda t: t if type(t) is Phrase else t[0], p)


def make_google_url(q):
    s = ''
    for w in q:
        if type(w) is Phrase:
            s += '"' + w.escape() + '"'
        else:
            s += w + '+'
    print 'search =', s
    return 'http://www.google.com/search?q=' + s


def is_same_word(word1, word2, first_try=True):
    if word1.lower() == word2.lower():
        return True
    if word1[-1] == 's' and re.sub('[^a-zA-Z0-9]', '', word1[:-1]).lower() == re.sub('[^a-zA-Z0-9]', '', word2).lower():  # plurals and 's
        return True
    if word1.split('\'')[0].lower() == word2.lower():
        return True
    if re.sub('[^a-zA-Z0-9]', '', word1).lower() == word2.lower():  # runner-up == runnerup
        return True
    if first_try:
        return is_same_word(word2, word1, False)
    return False


def remove_from_count(x, cnt):
    if type(x) is Phrase:
        for x1 in x.bare_words():
            remove_from_count(x1, cnt)
    else:
        for key in cnt.keys():
            if is_same_word(x, key):
                cnt.pop(key)
    return cnt


def blob_google(html, question):
    sts = map(lambda span: span.get_text(), html.find_all('span', 'st'))
    sts_blob = ' '.join(sts).lower()
    sts_blob = re.sub('[^\sa-z0-9]', '', sts_blob)
    cnt = collections.Counter(sts_blob.split())
    print sts_blob
    for x in common_english:
        if x in cnt:
            cnt.pop(x)
    for x in Phrase(None, question).bare_words():
        print 'remove', x
        remove_from_count(x, cnt)
    for x in cnt.keys():
        if nltk.pos_tag([x])[0][1] not in allow_important:
            cnt.pop(x)
    print cnt
    return cnt, re.sub('\s+', ' ', sts_blob)


def find_all_single(element, li):
    return [i for i, x in enumerate(li) if x == element]


def find_all_sublist(elements, li):
    return [i for i in range(len(li)) if li[i:i + len(elements)] == elements]


def find_related_words(dr, key, blob):
    blob = blob.split()
    positions = find_all_single(key, blob)

    i = 0

    def slice_blob(pos):
        if dr < 0:
            return tuple(blob[pos - i:pos])
        else:
            return tuple(blob[pos + 1:pos + i])
    while True:
        cnt = collections.Counter(map(slice_blob, positions))
        if cnt.most_common()[0][1] / float(sum(cnt.values())) > .5:  # more than half one phrase
            i += 1  # try more words
        else:
            i -= 1  # current i didn't meet threshold, decrement it
            cnt = collections.Counter(map(slice_blob, positions))
            return list(cnt.most_common()[0][0])  # take most common value, turn from tuple -> list


def google_it(question):
    html = BeautifulSoup(
        requests.get(make_google_url(important_words(question))).text)
    cnt, blob = blob_google(html, question)
    if len(cnt) == 0:
        raise Exception('Couldn\'t understand your sentence (blame nltk)')
    key_word = cnt.most_common()[0][0]
    before = find_related_words(-1, key_word, blob)
    after = find_related_words(1, key_word, blob)
    return 'what is ' + ' '.join(before) + ' ' + key_word + ' ' + ' '.join(after) + '?'

while True:
    print 'que?>',
    try:
        print google_it(raw_input())
    except EOFError:
        break
    except:
        import traceback
        traceback.print_exc()
