#!/usr/bin/env python
import nltk
import requests
from bs4 import BeautifulSoup
import re
import collections
import itertools

allow_important = ['NN', 'NNP', 'NNS', 'NNPS' ]
common_english = open('common-english-words').read().split()


class Phrase(object):
    def __init__(self, parent, sentence):
        self.parent = parent
        self.words = self.tokenize(sentence)

    def tokenize(self, sentence):
        toks = sentence
        if type(sentence) == str:
            toks = nltk.pos_tag(nltk.word_tokenize(sentence))  # do the inital pre-processing with nltk, but it has problems we need to fix.
        #problems:
        #   Contractions (eg don't) get split into do and n't. We stick those back together.
        #   Embedded phrases get split into `` PHRASE ''. We'll turn those into child Phrase instances instead.
        token_generator = itertools.chain(toks, itertools.repeat(None)) #toks, EOF
        fixed_toks = []
        while True:
            tok = token_generator.next()
            if tok == None:
                break
            elif tok[0] == '``':
                phrase = []
                while True:
                    tok1 = token_generator.next()
                    if tok1 == None:
                        break
                    elif tok1[0] == '\'\'':
                        fixed_toks.append(Phrase(self, phrase))
                        break
                    phrase.append(tok1)
            elif '\'' in tok[0]:
                fixed_toks[-1] = (fixed_toks[-1][0] + tok[0], fixed_toks[-1][1]) #contraction
            else:
                fixed_toks.append(tok)
        return fixed_toks

    def filter(self, lbda):
        return filter(lbda, self.words)

    def escape(self):
        s = ''
        for x in self.words:
            if type(x) is Phrase:
                s += '"' + x.escape() + '"+'
            else:
                s += x + '+'
        return s[0:-1]

    def bare_words(self):
        return map(lambda t: t[0], self.words)

    def __str__(self):
        return '"' + ', '.join(map(str, self.words)) + '"'

    def __repr__(self):
        return self.__str__()

def phrasify(sentence):
    return Phrase(None, sentence)


def important_words(question):
    p = phrasify(question).filter(lambda word: type(word) is Phrase or word[1] in allow_important)
    return map(lambda t: t[0], p)


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
    if word1 == word2:
        return True
    if word1[-1] == 's' and word1[:-1] == word2:
        return True
    if word1.split('\'') == word2:
        return True
    if first_try:
        return is_same_word(word2, word1, False)
    return False

def remove_from_count(x, cnt):
    if type(x) is Phrase:
        for x1 in x.words:
            remove_from_count(x1, cnt)
    else:
        for key in cnt.keys():
            if is_same_word(x, key):
                cnt.pop(key)
    return cnt


def blob_google(html, question):
    sts = map(lambda span: span.get_text(), html.find_all('span', 'st'))
    sts_blob = ' '.join(sts).lower()
    sts_blob = re.sub('[^"a-z0-9]', ' ', sts_blob)
    cnt = collections.Counter(sts_blob.split())
    for x in common_english:
        if x in cnt:
            cnt.pop(x)
    for x in Phrase(None, question).bare_words():
        remove_from_count(x, cnt)
    print cnt
    for x in cnt.keys():
        if nltk.pos_tag([x])[0][1] not in allow_important:
            print 'removing', x, nltk.pos_tag([x])
            cnt.pop(x)
    print cnt
    return cnt, re.sub('\s+', ' ', sts_blob)

def find_all_single(element, li):
    return [ i for i, x in enumerate(li) if x == element ]

def find_all_sublist(elements, li):
    return [ i for i in range(len(li)) if li[i:i+len(elements)] == elements ]

def find_related_words_before(key, blob):
    spb = blob.split()
    key_pos = find_all_single(key, spb)
    #Get what comes before for every occurance of the key word
    before_sents = map(lambda tup: spb[tup[0]:tup[1]], [ (key_pos[i - 1], key_pos[i]) if i > 0 else (0, key_pos[i]) for i in range(len(key_pos)) ])
    #Find what's the most common imm. preceding word
    before_cnt = collections.Counter(map(lambda sent: sent[-1], before_sents))
    mc = before_cnt.most_common()[0] #tuple(word, times)
    if mc[1] / float(sum(before_cnt.values())) > .5: #if percent is more than 50%, we've probably hit a related word
        #Now that we know what the (likely) related word is, we try and expand it into a phrase.
        accepted_before_sents = filter(lambda sent: sent[-1] == mc[0], before_sents)
        i = 1 #the number of words in the phrase
        while True:
            test_list = accepted_before_sents[-(i + 1):]
            if all(map(lambda sent: sent[-(i + 1):] == test_list, accepted_before_sents)):
                i += 1
            else:
                break
        return accepted_before_sents[0][-i:]
    return []

def find_related_words_after(key, blob):
    spb = blob.split()
    key_pos = find_all_single(key, spb)
    #Get what comes after for every occurance of the key word
    after_pos = [ (key_pos[i], key_pos[i + 1]) if i < len(key_pos) - 1 else (key_pos[i], len(spb)) for i in range(len(key_pos)) ]
    #tup[0]+1 so we don't get the key word
    after_sents = map(lambda tup: spb[tup[0]+1:tup[1]], after_pos)
    #Find what's the most common imm. preceding word
    after_cnt = collections.Counter(map(lambda sent: sent[0], after_sents))
    mc = after_cnt.most_common()[0] #tuple(word, times)
    if mc[1] / float(sum(after_cnt.values())) > .5: #if percent is more than 50%, we've probably hit a related word
        #Now that we know what the (likely) related word is, we try and expand it into a phrase.
        accepted_after_sents = filter(lambda sent: sent[0] == mc[0], after_sents)
        i = 1 #the number of words in the phrase
        while True:
            test_list = accepted_after_sents[i + 1:]
            if all(map(lambda sent: sent[i + 1:] == test_list, accepted_after_sents)):
                i += 1
            else:
                break
        return accepted_after_sents[0][i:]
    return []


def google_it(question):
    html = BeautifulSoup(requests.get(make_google_url(important_words(question))).text)
    cnt, blob = blob_google(html, question)
    if len(cnt) == 0:
        raise Exception('Couldn\'t understand your sentence (blame nltk)')
    key_word = cnt.most_common()[0][0]
    before = find_related_words_before(key_word, blob)
    after = find_related_words_after(key_word, blob)
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