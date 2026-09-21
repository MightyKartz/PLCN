"""Exact search aliases; editions remain separate and never imply a ROM checksum."""
# The first name is the existing search identity. Wiki titles identify articles,
# not a verified cover edition. The provider displays their image captions.
GAMES = [
    ('Romance of the Three Kingdoms IV - Wall of Fire', '三國志IV',
     ['三国志4', '三國志4', 'Sangokushi IV']),
    ('Romance of the Three Kingdoms V with Power Up Kit', '三國志V',
     ['三国志5威力加强版', '三國志5威力加強版', '三国志5X', 'Sangokushi V with Power Up Kit']),
    ('Three Kingdoms Yingjie Chuan', '三國志英傑傳',
     ['三国志英杰传', 'Sangokushi Eiketsuden']),
    ('Sword and Fairy', '仙劍奇俠傳 (遊戲)',
     ['仙剑奇侠传', '仙劍奇俠傳', 'The Legend of Sword and Fairy', 'Xian Jian Qi Xia Zhuan']),
    ('Uncharted Waters 2 - New Horizons (1995)', '大航海時代II',
     ['大航海时代2', '大航海時代2', 'Uncharted Waters 2 - New Horizons', 'Daikoukai Jidai II']),
    ('Flame Dragon 2 - Legend of Golden Castle', '炎龍騎士團II 黃金城之謎',
     ['炎龙骑士团2黄金城之谜', 'Flame Dragon II Legend of Golden Castle', 'Yan Long Qi Shi Tuan II - Huang Jin Cheng Zhi Mi']),
    ('Xuan-Yuan Sword - Dance of the Maple Leaves', '軒轅劍外傳 楓之舞',
     ['轩辕剑外传：枫之舞', '軒轅劍外傳：楓之舞', 'Xuan Yuan Jian Wai Zhuan - Feng Zhi Wu']),
    ('Jin Yong Qun Xia Chuan', '金庸群俠傳',
     ['金庸群侠传', 'Jin Yong Qun Xia Zhuan', 'Heroes of Jin Yong']),
]


def key(name):
    # Retain edition qualifiers, including parenthesized ones.
    return ''.join(c for c in str(name).casefold() if c.isalnum())


def game(query):
    return next((row for row in GAMES if key(query) in {key(n) for n in [row[0], *row[2]]}), None)


def search_names(system, query):
    row = game(query) if system == 'DOS' else None
    # The article for ROTK V also covers the base game; that article title
    # cannot be used as an official-gallery alias for the Power Up Kit.
    return list(dict.fromkeys([query, row[0], *row[2], *([] if 'Power Up Kit' in row[0] else [row[1]])])) if row else [query]
