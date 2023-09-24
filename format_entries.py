from feedparser import FeedParserDict


def _fix_title(entry: FeedParserDict):
    title = entry.title

    if entry.updated != entry.published:
        title += ' *(UPDATED)*'

    entry.title = title


def _fix_abstract(entry: FeedParserDict):
    abstract = entry.summary
    abstract = abstract.replace('\n', ' ')
    abstract = abstract.replace('  ', ' ')
    entry.summary = abstract


def _fix_authors(entry: FeedParserDict):
    authors = entry.authors
    authors = ', '.join([author.name for author in authors])

    entry.authors = authors


def _fix_equations(entry: FeedParserDict):
    # TODO: Check if this is still working with the new feedparser
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


def fix_entry(entry: FeedParserDict):
    _fix_title(entry)
    _fix_abstract(entry)
    _fix_authors(entry)
    _fix_equations(entry)


def write_article(entry: FeedParserDict, f, index: int, n_total: int):
    f.write(f'({index + 1} / {n_total})\n\n')
    f.write(f'Title: **{entry.title}**\n\n')
    f.write(f'Author(s): {entry.authors}\n\n')
    f.write(f'Abstract: {entry.summary}\n\n')
    f.write(f'{entry.id}\n\n')
    f.write('-' * 50)
    f.write('\n\n')