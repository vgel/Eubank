import itertools

def is_likely_url(word):
    for x in ['.com', '.net', '.org', '.gov', '.mil']:
        if word.endswith(x):
            return x
    return None

def findall_list(element, li):
    return [ i for i, x in enumerate(li) if x == element ]

def grouper(n, iterable, padvalue=None):
  return itertools.izip_longest(*[iter(iterable)]*n, fillvalue=padvalue)