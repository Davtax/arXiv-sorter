import feedparser
import datetime
import os


def _find_and_replace(text: str, keyword: str, start: str, finish: str = None) -> str:
    if finish is None:
        finish = start

    keyword = keyword.lower()

    length_replace = len(start)

    last_index = -1
    while True:
        last_index = text.lower().find(keyword, last_index + 1)
        if last_index == -1:
            break

        else:
            text = text[:last_index] + start + text[last_index:last_index + len(keyword)] + finish + text[
                                                                                                     last_index + len(
                                                                                                         keyword):]

            last_index += length_replace

    return text


def _fix_title(entry: dict):
    title = entry.title

    index = title.find('. (arXiv')
    if 'UPDATED' in title[index:]:
        entry.updated = True
    else:
        entry.updated = False

    title = title[: index]
    if entry.updated:
        title += ' <span style="color:yellow">(UPDATED)</span>'
    entry.title = title


def _fix_abstract(entry: dict):
    abstract = entry.summary[3:-5]
    abstract = abstract.replace('\n', ' ')
    abstract = abstract.replace('  ', ' ')
    entry.summary = abstract


def _fix_authors(entry: dict):
    authors = entry.author.replace('</a>', '')

    index_0 = authors.find('<a href=')
    while index_0 != -1:
        index_f = authors.find('">', index_0)
        authors = authors[:index_0] + authors[index_f + 2:]
        index_0 = authors.find('<a href=')

    entry.author = authors


def _fix_equations(entry: dict):
    abstract = entry.summary

    index_0 = abstract.find('$')
    while True:

        if abstract[index_0 + 1] == ' ':
            abstract = abstract[:index_0 + 1] + abstract[index_0 + 2:]

        index_1 = abstract.find('$', index_0 + 1)

        if abstract[index_1 - 1] == ' ':
            abstract = abstract[:index_1 - 1] + abstract[index_1:]
            index_1 += -1

        if abstract[index_1 + 1].isnumeric():
            abstract = abstract[:index_1 + 1] + ' ' + abstract[index_1 + 1:]

        index_0 = abstract.find('$', index_1 + 1)

        if index_0 == -1 or index_1 == -1:
            break

    abstract = abstract.replace('&lt;', '<')
    abstract = abstract.replace('&gt;', '>')

    abstract = abstract.replace('  ', ' ')
    entry.summary = abstract


def fix_entry(entry: dict):
    _fix_title(entry)
    _fix_abstract(entry)
    _fix_authors(entry)
    _fix_equations(entry)


def find_keywords(entry: dict, keyword: str = None, author: str = None) -> (dict, bool):
    keyword_found = False

    if keyword is not None:
        if keyword.lower() in entry.title.lower():
            entry.title = _find_and_replace(entry.title, keyword, keyword_title_enclosed[0], keyword_title_enclosed[1])
            keyword_found = True

        if keyword.lower() in entry.summary.lower():
            entry.summary = _find_and_replace(entry.summary, keyword, keyword_abstract_enclosed[0],
                                              keyword_abstract_enclosed[1])
            keyword_found = True

    if author is not None:
        if author.lower() in entry.author.lower():
            entry.author = _find_and_replace(entry.author, author, keyword_author_enclosed[0],
                                             keyword_author_enclosed[1])
            keyword_found = True

    return entry, keyword_found


def sort_articles(entries: list, keywords: list, authors: list) -> (list, list):
    sorted_entries = []
    rest_entries = []

    indices_sorted = []
    for keyword in keywords:
        for i, entry in enumerate(entries):
            entry, keyword_found = find_keywords(entry, keyword=keyword)
            if keyword_found:
                if i not in indices_sorted:
                    indices_sorted.append(i)
                    sorted_entries.append(entry)

    for author in authors:
        for i, entry in enumerate(entries):
            entry, keyword_found = find_keywords(entry, author=author)
            if keyword_found:
                if i not in indices_sorted:
                    indices_sorted.append(i)
                    sorted_entries.append(entry)

    for i, entry in enumerate(entries):
        if i not in indices_sorted:
            if not entry.updated:
                rest_entries.append(entry)

    return sorted_entries + rest_entries


def read_file(file_name: str) -> list:
    with open(file_name, 'r') as f:
        lines = f.read()

    lines = lines.split('\n')

    unique_lines = []
    for i in range(len(lines)):
        line = lines[i].lower()

        if len(line) == 0:
            continue
        elif line[0] == '#':
            continue
        else:
            if line not in unique_lines:
                unique_lines.append(line)

    return unique_lines


def write_article(entry, f, index, n_total):
    f.write(f'({index + 1} / {n_total})\n\n')
    f.write(f'Title: **{entry.title}**\n\n')
    f.write(f'Author(s): {entry.author}\n\n')
    f.write(f'Abstract: {entry.summary}\n\n')
    f.write(f'{entry.id}\n\n')
    f.write('-' * 50)
    f.write('\n\n')


def main(cat_name: str, ids: list) -> list:
    print('Parsing RSS feed...')
    NewsFeed = feedparser.parse('https://export.arxiv.org/rss/' + cat_name)
    entries = NewsFeed.entries
    print('Done.\n')

    date = NewsFeed.feed.updated
    date = date[:date.find('T')]

    print('Fixing entries...')
    [fix_entry(entry) for entry in entries]

    if ids is not None:
        for i in range(len(entries) - 1, -1, -1):
            if entries[i].id in ids:
                del entries[i]
            else:
                ids.append(entries[i].id)

    print('Done.\n')

    print('Sorting entries...')
    entries = sort_articles(entries, keywords, authors)
    print('Done.\n')

    print('Writing abstracts...')
    n_total = len(entries)
    with open(f'abstracts/{date}_{cat_name}.md', 'w') as f:
        [write_article(entries[index], f, index, n_total) for index in range(n_total)]

        ct = datetime.datetime.now()
        f.write(f'\n\n*Last updated: {ct.strftime("%d %B %Y %H:%M:%S")}*')
    print('Done.\n')

    return ids


if not os.path.exists('abstracts'):
    os.mkdir('abstracts')

keyword_title_enclosed = ['<span style="color:red"><u>', '</u></span>']
keyword_abstract_enclosed = ['<span style="color:red">**', '**</span>']
keyword_author_enclosed = ['<span style="color:green"><u>', '</u></span>']

keywords = read_file('keywords.txt')
authors = read_file('authors.txt')
categories = read_file('categories.txt')

# TODO: add option to search for multiple keywords in same article
# TODO: Captital letters with accent does not work
# TODO: Math command \dag and \ddag does not render properly
# TODO: When using ``___'' in abstract, it does render as code
# TODO: How to get previous mail lists?

with open('categories.txt') as f:
    repeat_bool = f.readline()[:-1].split('=')[-1]

if repeat_bool == 'True' or len(categories) == 1:
    ids = None
elif repeat_bool == 'False':
    ids = []

for cat_name in categories:
    ids = main(cat_name, ids)
