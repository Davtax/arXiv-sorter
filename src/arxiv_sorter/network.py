"""
Concurrent HTTP requests to arXiv.
"""
import re

import grequests
import requests

from arxiv_sorter.console import Progressbar


class ProgressSession:
    def __init__(self, urls: list[str]):
        self.pbar = Progressbar(len(urls), prefix='Progress:')
        self.urls = urls

    def update(self, r=None, *args, **kwargs):
        if not r.is_redirect:
            self.pbar.update()

    def __enter__(self):
        sess = requests.Session()
        sess.hooks['response'].append(self.update)
        return sess

    def __exit__(self, *args):
        self.pbar.close()


def get_urls_async(urls: list[str], progress_bar: bool = True) -> list[requests.Response]:
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}

    if progress_bar:
        with ProgressSession(urls) as sess:
            rs = (grequests.get(url, session=sess, headers=headers) for url in urls)

            return grequests.map(rs, size=5)
    else:
        rs = (grequests.get(url, headers=headers) for url in urls)
        return grequests.map(rs, size=5)


def get_image_urls(ids: list[str]) -> list[str]:
    urls = [f'https://arxiv.org/html/{id_}' for id_ in ids]
    results = get_urls_async(urls)

    image_urls = []
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
        png_name = re.search(r'src=.*?\.png', fp[index_0:index_f]).group().replace('src="', '')
        return png_name
