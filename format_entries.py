from feedparser import FeedParserDict

from dates_functions import obtain_date


def _remove_white_space(text: str) -> str:
    index = text.find('  ')
    while index != -1:
        text = text.replace('  ', ' ')
        index = text.find('  ')
    return text


def _fix_title(entry: FeedParserDict):
    title = entry.title

    title = title.replace('\n', ' ')
    title = _remove_white_space(title)
    title = title.replace('`', "'")

    if entry.updated != entry.published:
        title += ' *(UPDATED)*'
        entry['updated_bool'] = True
    else:
        entry['updated_bool'] = False

    entry.title = title


def _fix_abstract(entry: FeedParserDict):
    abstract = entry.summary
    abstract = abstract.replace('\n', ' ')
    abstract = _remove_white_space(abstract)
    abstract = abstract.replace('`', "'")

    entry.summary = abstract


def _fix_authors(entry: FeedParserDict):
    authors = entry.authors
    authors = ', '.join([author.name for author in authors])

    entry.authors = authors


def _fix_equation_inner(text: str) -> str:
    index_0 = text.find('$')
    while index_0 != -1:
        if text[index_0 + 1] == ' ':
            text = text[:index_0 + 1] + text[index_0 + 2:]

        index_1 = text.find('$', index_0 + 1)
        if index_1 == -1:
            break

        if text[index_1 - 1] == ' ':
            text = text[:index_1 - 1] + text[index_1:]
            index_1 += -1

        try:
            if text[index_1 + 1].isnumeric():
                text = text[:index_1 + 1] + ' ' + text[index_1 + 1:]
        except IndexError:
            pass

        index_0 = text.find('$', index_1 + 1)

    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')

    text = _remove_white_space(text)
    return text


def _fix_equations(entry: FeedParserDict):
    entry.summary = _fix_equation_inner(entry.summary)
    entry.title = _fix_equation_inner(entry.title)


def _fix_date(entry: FeedParserDict):
    date = entry.updated

    ct = obtain_date(date)
    entry.updated = ct.strftime("%a, %d %b %Y %H:%M:%S GMT")


def fix_entry(entry: FeedParserDict):
    _fix_title(entry)
    _fix_abstract(entry)
    _fix_authors(entry)
    _fix_equations(entry)
    _fix_date(entry)


def write_article(entry: FeedParserDict, f, index: int, n_total: int):
    f.write(f'({index + 1} / {n_total})\n\n')
    f.write(f'Title: **{entry.title}**\n\n')

    if ',' in entry.authors:
        f.write(f'Authors: {entry.authors}\n\n')
    else:
        f.write(f'Author: {entry.authors}\n\n')

    f.write(f'Abstract: {entry.summary}\n\n')
    f.write(f'{entry.id}\n\n')
    f.write(f'<span style="font-size:0.9em;">*Updated: {entry.updated}*</span>\n\n')
    f.write('---')
    f.write('\n')
