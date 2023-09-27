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
    text = text[:index_0] + enclosure[0] + text[index_0:index_f] + enclosure[1] + text[index_f:]

    return text


def _find_text(text: str, keywords: List[str]) -> Tuple[List[Tuple[int, int, str]], int]:
    keyword_index = len(keywords) + 1
    text = text.lower()
    indices = []
    for i, keyword in enumerate(keywords):
        if type(keyword) is str:  # Single keyword
            index = text.find(keyword)
            while index != -1:
                keyword_index = min(keyword_index, i)
                indices.append((index, index + len(keyword), 'single'))
                index = text.find(keyword, index + 1)
        elif type(keyword) is list:  # Group of keywords
            indices_group = []
            for keyword_i in keyword:
                index = text.find(keyword_i)
                if index == -1:
                    break
                indices_temp = []
                while index != -1:
                    indices_temp.append((index, index + len(keyword_i), 'group'))
                    index = text.find(keyword_i, index + 1)
                indices_group.append(indices_temp)
            if len(indices_group) == len(keyword):
                indices += [item for sublist in indices_group for item in sublist]

    indices = sorted(indices, key=lambda x: x[0])

    if keyword_index == len(keywords) + 1:
        keyword_index = None

    return indices, keyword_index


def _find_overlaps(indices):
    # Check if keyword is inside another keyword
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
                index_kept = j

            if index_kept is not None:
                temp = list(indices[index_kept])
                if kind_i == kind_j:
                    temp[2] = kind_i
                else:
                    temp[2] = 'overlap'
                indices[index_kept] = tuple(temp)

    indices = [indices[i] for i in range(len(indices)) if i not in indices_to_remove]
    return indices


def _find_title(title: str, keywords: List[str]) -> Tuple[str, int]:
    indices, keyword_index = _find_text(title, keywords)
    indices = _find_overlaps(indices)

    for index_0, index_f, _ in indices[::-1]:
        title = _replace_text(title, index_0, index_f, TitleEnclosure)
    return title, keyword_index


def _find_keywords(abstract: str, keywords: List[str]) -> Tuple[str, int]:
    indices, keyword_index = _find_text(abstract, keywords)
    indices = _find_overlaps(indices)

    for index_0, index_f, kind in indices[::-1]:
        if kind == 'single':
            enclosure = AbstractEnclosure
        elif kind == 'group':
            enclosure = GroupEnclosure
        elif kind == 'overlap':
            enclosure = OverlapEnclosure
        else:
            raise ValueError(f'Unknown keyword kind: {kind}')

        abstract = _replace_text(abstract, index_0, index_f, enclosure)

    return abstract, keyword_index


def _find_authors(authors_list: str, authors: List[str]) -> Tuple[str, int]:
    author_index = len(authors) + 1
    for i, author in enumerate(authors):
        index_0 = unidecode(authors_list.lower()).find(author)

        if index_0 != -1:
            index_f = index_0 + len(author)
            authors_list = _replace_text(authors_list, index_0, index_f, AuthorEnclosure)
            author_index = min(author_index, i)

    if author_index == len(authors) + 1:
        author_index = None

    return authors_list, author_index


def sort_articles(entries: List[FeedParserDict], keywords: List[str], authors: List[str]) -> List[FeedParserDict]:
    max_index = len(keywords) + len(authors) + 1
    for entry in entries:
        title, keyword_index_title = _find_title(entry.title, keywords)
        abstract, keyword_index_abstract = _find_keywords(entry.summary, keywords)
        authors_list, author_index = _find_authors(entry.authors, authors)

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
