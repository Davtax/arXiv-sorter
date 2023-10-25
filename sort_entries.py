from typing import List, Tuple
from feedparser import FeedParserDict
from unidecode import unidecode

# Define the strings to be replaced in the markdown file
TitleEnclosure = ['<span style="color:red"><u>', '</u></span>']
AuthorEnclosure = ['<span style="color:green"><u>', '</u></span>']
AbstractEnclosure = ['<span style="color:red"><B>', '</B></span>']
GroupEnclosure = ['<span style="color:yellow"><B><u>', '</u></B></span>']
OverlapEnclosure = ['<span style="color:green"><B><u>', '</u></B></span>']


def _replace_text(text: str, index_0, index_f, enclosure: List[str]) -> str:
    """
    Replace the text between index_0 and index_f with a given enclosure and the beginning and end of the text.
    """
    text = text[:index_0] + enclosure[0] + text[index_0:index_f] + enclosure[1] + text[index_f:]

    return text


def _find_single_keyword(text: str, keyword: str) -> List[Tuple[int, int, str]]:
    """
    Find the keyword in the text and return the indices where it is found.
    """
    index = text.find(keyword)
    indices_temp = []
    while index != -1:
        indices_temp.append((index, index + len(keyword), 'single'))
        index = text.find(keyword, index + 1)

    return indices_temp


def _find_group_keywords(text: str, keywords: List[str]) -> List[Tuple[int, int, str]]:
    """
    Find the keywords when appear at the same time and return the indices where they are found.
    """
    indices_total = []
    indices_group = []
    for keyword_i in keywords:
        index = text.find(keyword_i)
        if index == -1:
            break
        indices_temp = []
        while index != -1:
            indices_temp.append((index, index + len(keyword_i), 'group'))
            index = text.find(keyword_i, index + 1)
        indices_group.append(indices_temp)
    if len(indices_group) == len(keywords):
        indices_total += [item for sublist in indices_group for item in sublist]

    return indices_total


def _find_text(text: str, keywords: List[str]) -> Tuple[List[Tuple[int, int, str]], int]:
    """
    Find the keywords in the text and return the indices where they are found. The indices are sorted by the
    appearance of the keywords in the text.
    The text is normalized in lower case.
    """
    keyword_index = len(keywords) + 1
    text = text.lower()
    indices = []
    for i, keyword in enumerate(keywords):
        if type(keyword) is str:  # Single keyword
            indices_temp = _find_single_keyword(text, keyword)
            if indices_temp:
                indices += indices_temp
                keyword_index = min(keyword_index, i)
        elif type(keyword) is list:  # Group of keywords
            indices_temp = _find_group_keywords(text, keyword)
            if indices_temp:
                indices += indices_temp
                keyword_index = min(keyword_index, i)

    indices = sorted(indices, key=lambda x: x[0])

    if keyword_index == len(keywords) + 1:
        keyword_index = None

    return indices, keyword_index


def _find_overlaps(indices):
    """
    Check if keyword is inside another keyword.
    """
    indices_to_remove = []
    for i in range(len(indices)):
        if i in indices_to_remove:
            continue
        index_0_i, index_f_i, kind_i = indices[i]
        for j in range(i + 1, len(indices)):
            index_0_j, index_f_j, kind_j = indices[j]
            index_kept = None
            if index_0_j > index_f_i:  # Keywords don't overlap
                break
            elif index_0_i < index_0_j < index_f_i < index_f_j:
                # Keywords overlap and i is to the left of j
                indices_to_remove.append(i)
                indices_to_remove.append(j)
                indices.append((index_0_i, index_f_j, 'overlap'))
                index_kept = len(indices) - 1
            elif index_0_i <= index_0_j and index_f_i >= index_f_j:  # Keyword j is inside keyword i
                indices_to_remove.append(j)
                index_kept = i
            elif index_0_i >= index_0_j and index_f_i <= index_f_j:  # Keyword i is inside keyword j
                indices_to_remove.append(i)
                index_kept = j  # TODO: Check if this condition is necessary

            if index_kept is not None:  # TODO: Check if this condition is necessary
                temp = list(indices[index_kept])
                if kind_i == kind_j:
                    temp[2] = kind_i
                else:
                    temp[2] = 'overlap'
                indices[index_kept] = tuple(temp)

    indices = [indices[i] for i in range(len(indices)) if i not in indices_to_remove]
    return indices


def _find_and_add(text, keywords, enclosure):
    """
    Find the keywords in the text and add them with the given enclosure.
    """
    indices, keyword_index = _find_text(text, keywords)
    indices = _find_overlaps(indices)  # Fix the indices if there are overlaps

    for index_0, index_f, kind in indices[::-1]:  # Reverse order to avoid problems with the indices
        if type(enclosure) is dict:
            enclosure_str = enclosure[kind]
        else:
            enclosure_str = enclosure

        text = _replace_text(text, index_0, index_f, enclosure_str)
    return text, keyword_index


def sort_articles(entries: List[FeedParserDict], keywords: List[str], authors: List[str]) -> List[FeedParserDict]:
    max_index = len(keywords) + len(authors) + 1
    for entry in entries:
        title_enclosure = 'TitleEnclosure'
        abstract_enclosure = {'single': AbstractEnclosure, 'group': GroupEnclosure, 'overlap': OverlapEnclosure}
        authors_enclosure = 'AuthorEnclosure'

        title, keyword_index_title = _find_and_add(entry.title, keywords, title_enclosure)
        abstract, keyword_index_abstract = _find_and_add(entry.summary, keywords, abstract_enclosure)
        authors_list, author_index = _find_and_add(entry.authors, authors, authors_enclosure)

        keyword_index = min(
            value for value in [keyword_index_title, keyword_index_abstract, max_index] if value is not None)
        if keyword_index == max_index:
            keyword_index = None

        if keyword_index is not None:
            entry['index'] = keyword_index
        elif author_index is not None:
            entry['index'] = len(keywords) + author_index
        else:
            entry['index'] = max_index

        if entry['updated_bool'] and entry['index'] == max_index:
            entry['index'] += 1

        entry.title = title
        entry.summary = abstract
        entry.authors = authors_list

    return sorted(entries, key=lambda x: x['index'])
