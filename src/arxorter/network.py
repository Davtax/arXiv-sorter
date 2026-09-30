"""
Concurrent HTTP requests to arXiv, with a pool of threads.
"""
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from arxorter.console import Progressbar

MAX_WORKERS = 5  # Simultaneous requests
TIMEOUT = 60  # seconds
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}


def _get(url: str) -> requests.Response | None:
    """
    GET request, or None if it failed (no connection, timeout, ...).
    """
    try:
        return requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None


def get_urls_async(urls: list[str], progress_bar: bool = True) -> list[requests.Response | None]:
    """
    Request the urls concurrently. The responses are in the same order as the urls, with None for the failed ones.
    """
    pbar = Progressbar(len(urls), prefix='Progress:') if progress_bar and urls else None
    responses: list[requests.Response | None] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for response in executor.map(_get, urls):  # Yields in the order of the urls
            responses.append(response)
            if pbar is not None:
                pbar.update()

    if pbar is not None:
        pbar.close()
    return responses


def get_image_urls(ids: list[str]) -> list[str | None]:
    urls = [f'https://arxiv.org/html/{id_}' for id_ in ids]
    results = get_urls_async(urls)

    image_urls: list[str | None] = []
    for id_, result in zip(ids, results, strict=True):
        path = get_image(result)
        if path == '':
            image_urls.append(None)
        else:
            image_urls.append(f'https://arxiv.org/html/{id_}/{path}')

    return image_urls


def get_image(response: requests.Response | None) -> str:
    """
    Get the png image from the url and return its source
    """
    if response is None:
        return ''

    fp = response.text

    match = re.search(r'<img.*?src=.*?\.png.*?>', fp)
    if match is None:
        return ''
    else:
        index_0, index_f = match.span()
        source = re.search(r'src=.*?\.png', fp[index_0:index_f])
        png_name = source.group().replace('src="', '') if source is not None else ''
        return png_name
