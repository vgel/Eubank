#!/usr/bin/env python
from bs4 import BeautifulSoup
from HTMLParser import HTMLParser
import json
import re
import requests
import sys

url = 'http://www.j-archive.com/showgame.php?game_id={0}'


def unescape(s):
    return HTMLParser().unescape(s)  # ew


def get_html(game_id):
    text = unicode(requests.get(url.format(game_id)).content.decode('ISO-8859-1'))
    #print text
    return BeautifulSoup(text)


def is_game_tag(tag):
    return tag and tag.name == 'div' and tag.has_key('onmouseover')


def tag_to_clue(tag):
    clue = re.sub('\\\\(.)', '\g<1>', re.match("""toggle\('(.*?)'\, '(.*?)', '(.*?)'\)""", tag['onmouseout']).group(3))
    answer = BeautifulSoup(unescape(tag['onmouseover'])).find('i')
    if answer:
        return (clue, answer.text)
    answer = BeautifulSoup(unescape(tag['onmouseover'])).find('em')
    if answer:
        return (clue, answer.text)
    print BeautifulSoup(unescape(tag['onmouseover'])).prettify()
    raise Exception('Couldn\'t find answer')

with open(sys.argv[2], 'w') as f:
    print 'start!'
    for i in xrange(1, int(sys.argv[1]) + 1):
        print i
        for question in map(tag_to_clue, get_html(i).find_all(is_game_tag)):
            if '</a>' in question[0]: #doesn't understand links
                continue
            try:
                s = u'~!clue {0}\n~!answer {1}\n\n'.format(*question)
                f.write(s)
            except: #funky coding errors'
                pass

