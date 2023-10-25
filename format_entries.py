from feedparser import FeedParserDict

from dates_functions import obtain_date


def _remove_white_space(text: str) -> str:
    """
    Remove duplicate white spaces from a string.
    """
    index = text.find('  ')
    while index != -1:  # Iterate until there are no more duplicate white spaces
        text = text.replace('  ', ' ')
        index = text.find('  ')
    return text


def _fix_title(entry: FeedParserDict):
    """
    Fix the title to remove white spaces and other uncommon characters.
    """
    title = entry.title

    title = title.replace('\n', ' ')  # The raw data contains carriage returns
    title = _remove_white_space(title)
    title = title.replace('`', "'")

    if entry.updated != entry.published:  # If the entry has been updated, so it is not new
        title += ' *(UPDATED)*'
        entry['updated_bool'] = True
    else:
        entry['updated_bool'] = False

    entry.title = title


def _fix_abstract(entry: FeedParserDict):
    """
    Fix the abstract to remove white spaces and other uncommon characters.
    """
    abstract = entry.summary
    abstract = abstract.replace('\n', ' ')  # The raw data contains carriage returns
    abstract = _remove_white_space(abstract)
    abstract = abstract.replace('`', "'")

    entry.summary = abstract


def _fix_authors(entry: FeedParserDict):
    """
    Join the authors in a single string.
    """
    authors = entry.authors
    authors = ', '.join([author.name for author in authors])

    entry.authors = authors


def _fix_equation_inner(text: str) -> str:
    """
    Fix the equations to proper visualization in the markdown file.
    """
    index_0 = text.find('$')  # Find the beginning equation
    while index_0 != -1:
        if text[index_0 + 1] == ' ':  # Remove the white space after the first $
            text = text[:index_0 + 1] + text[index_0 + 2:]

        index_1 = text.find('$', index_0 + 1)  # Find the end of the equation
        if index_1 == -1:
            break

        if text[index_1 - 1] == ' ':  # Remove the white space before the end of the equation
            text = text[:index_1 - 1] + text[index_1:]
            index_1 += -1

        try:
            if text[index_1 + 1].isnumeric():  # Add a white space after the end of the equation if there is a number
                text = text[:index_1 + 1] + ' ' + text[index_1 + 1:]
        except IndexError:
            pass

        index_0 = text.find('$', index_1 + 1)  # Find the beginning of the next equation

    # Replace common HTML characters which are not supported by markdown
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')

    text = _remove_white_space(text)
    return text


def _fix_equations(entry: FeedParserDict):
    """
    Fix the equations that appear both in the title and the abstract.
    """
    entry.summary = _fix_equation_inner(entry.summary)
    entry.title = _fix_equation_inner(entry.title)


def _fix_date(entry: FeedParserDict):
    """
    Fix the date to the proper format.
    """
    date = entry.updated

    ct = obtain_date(date)
    entry.updated = ct.strftime("%a, %d %b %Y %H:%M:%S GMT")


def fix_entry(entry: FeedParserDict):
    """
    Fix the entry to proper visualization in the markdown file.
    """
    _fix_title(entry)
    _fix_abstract(entry)
    _fix_authors(entry)
    _fix_equations(entry)
    _fix_date(entry)


def write_article(entry: FeedParserDict, f, index: int, n_total: int):
    """
    Write the article to the markdown file.
    """
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
