import re

from feedparser import FeedParserDict
from unidecode import unidecode

# Define the strings to be replaced in the markdown file
TitleEnclosure = ['<span style="color:orange"><u>', '</u></span>']
AuthorEnclosure = ['<span style="color:green"><u>', '</u></span>']
AbstractEnclosure = ['<span style="color:red"><B>', '</B></span>']


def _find_overlaps(indices: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """
    Merge the (start, end) spans, sorted by start, that overlap or are inside another span, so each piece of text is
    highlighted only once.
    """
    indices_to_remove = []
    for i in range(len(indices)):
        if i in indices_to_remove:
            continue
        index_0_i, index_f_i = indices[i]
        for j in range(i + 1, len(indices)):
            index_0_j, index_f_j = indices[j]
            if index_0_j > index_f_i:  # Keywords don't overlap
                break
            elif index_0_i < index_0_j < index_f_i < index_f_j:
                # Keywords overlap and i is to the left of j
                indices_to_remove.append(i)
                indices_to_remove.append(j)
                indices.append((index_0_i, index_f_j))
            elif index_0_i <= index_0_j and index_f_i >= index_f_j:  # Keyword j is inside keyword i
                indices_to_remove.append(j)
            elif index_0_i >= index_0_j and index_f_i <= index_f_j:  # Keyword i is inside keyword j
                indices_to_remove.append(i)

    indices = [indices[i] for i in range(len(indices)) if i not in indices_to_remove]
    return indices


def _find_re(text: str, keywords_list: list[str], enclosure: list[str], normalize: bool = False) -> tuple[
    str, int | None]:
    """
    Highlight in `text` every match of the keywords, and return the index of the first line in `keywords_list` that
    matches (None if nothing matches). Keywords joined by '&' must all be present in the text for the line to match.
    """
    text_regular = text.lower()
    if normalize:
        text_regular = unidecode(text_regular)
        text_regular = text_regular.replace('-', ' ')

    keyword_index = len(keywords_list) + 1
    matches = []
    for i, keyword_list in enumerate(keywords_list):
        keywords = re.split('&', keyword_list)

        if all(re.search(keyword, text_regular) for keyword in keywords):
            keyword_index = min(keyword_index, i)
            for keyword in keywords:
                matches += list(re.finditer(keyword, text_regular, re.IGNORECASE))

    matches = sorted(matches, key=lambda x: x.start(), reverse=False)
    indices = [(match.start(), match.end()) for match in matches]
    indices = _find_overlaps(indices)
    for index_0, index_f in indices[::-1]:
        text = text[:index_0] + enclosure[0] + text[index_0:index_f] + enclosure[1] + text[index_f:]

    if keyword_index == len(keywords_list) + 1:
        keyword_index = None

    return text, keyword_index


def sort_articles(entries: list[FeedParserDict], keywords_list: list[str], authors_list: list[str]) -> list[
    FeedParserDict]:
    """
    Highlight the keywords and authors, and sort the entries by the priority of the first matching line.
    Each entry gets an `index`: positive for matches (higher first), 0 for new entries without matches and -1 for
    updated entries without matches.
    """
    max_index = len(keywords_list) + len(authors_list) + 1

    for entry in entries:
        title, keyword_index_title = _find_re(entry.title, keywords_list, TitleEnclosure)
        abstract, keyword_index_abstract = _find_re(entry.summary, keywords_list, AbstractEnclosure)
        authors, author_index = _find_re(entry.authors, authors_list, AuthorEnclosure, normalize=True)

        index_keyword = min(
            value for value in [keyword_index_title, keyword_index_abstract, max_index] if value is not None)
        index_author = min(value for value in [author_index, max_index] if value is not None)

        if index_keyword != max_index and index_author != max_index:  # If both keyword and author are found
            index = index_keyword  # Group by keyword
        else:  # If only one of the two, or none, is found
            index = min(index_keyword, index_author)

        if entry.updated_bool and index == max_index:  # If the entry has been updated and no keyword or author is found
            index += 1

        entry['index'] = max_index - index
        entry['last_new'] = False  # Initialize the last_new attribute, it will be updated later

        entry['title'] = title
        entry['summary'] = abstract
        entry['authors'] = authors

    return sorted(entries, key=lambda x: x['index'], reverse=True)
