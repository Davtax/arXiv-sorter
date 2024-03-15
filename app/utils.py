from time import sleep, time
import sys
import requests
import grequests


def timing_message(total_time: int, message: str, step: int = 1):
    for i in range(0, total_time, step):
        print(f'Waiting {total_time - i} seconds {message}', end='\r')
        sleep(step)
    print('')


def question(message) -> bool:
    """
    Make a question and return True or False depending on the answer of the user. There is only two possible answers
    y -> yes or	n -> no. If the answer is none of this two the question is repeated until a good answer is given.
    If not message is provided, then the default overwriting file message is printed, with the file name provided.
    """
    temp = input(message + ' [y]/n: ').lower()  # Ask for an answer by keyword input

    if temp == 'y' or temp == '':
        return True
    elif temp == 'n':
        return False
    else:  # If the answer is not correct
        print('I didn\'t understand your answer.')
        return question(message)  # The function will repeat until a correct answer if provided


class ProgressSession:
    def __init__(self, urls):
        self.pbar = Progressbar(len(urls), prefix='Progress:')
        self.urls = urls

    def update(self, r, *args, **kwargs):
        if not r.is_redirect:
            self.pbar.update()

    def __enter__(self):
        sess = requests.Session()
        sess.hooks['response'].append(self.update)
        return sess

    def __exit__(self, *args):
        self.pbar.close()


def get_urls_async(urls):
    with ProgressSession(urls) as sess:
        rs = (grequests.get(url, session=sess) for url in urls)

        return grequests.map(rs)


def get_image_urls(ids: list[str]) -> list[str]:
    urls = [f'https://arxiv.org/html/{id_}' for id_ in ids]
    results = get_urls_async(urls)

    image_urls = []
    for id_, result in zip(ids, results):
        path = get_image(result)
        if path == '':
            image_urls.append(None)
        else:
            image_urls.append(f'https://arxiv.org/html/{id_}/{path}')

    return image_urls


def get_image(response) -> str:
    """
    Get the png image from the url and return its source
    """
    if response is None:
        return ''
    
    fp = response.text
    index_f = fp.find('.png')
    index_0 = fp.rfind('src="', 0, index_f + 4)

    if index_0 == -1 or index_f == -1:
        return ''

    return fp[index_0 + 5:index_f + 4]


class Progressbar:
    def __init__(self, count: int, prefix: str = "", size: int = 40, out=sys.stdout):
        self.count = count
        self.current = 0
        self.start = time()

        self.size = size
        self.prefix = prefix
        self.out = out

    def update(self, j=1):
        self.current += j
        x = int(self.size * self.current / self.count)
        remaining = ((time() - self.start) / self.current) * (self.count - self.current)

        rate = self.current / (time() - self.start)

        mins, sec = divmod(remaining, 60)
        time_str = f"{int(mins):02}:{int(sec):02}"

        current_time = time() - self.start
        mins_current, sec_current = divmod(current_time, 60)
        time_str_current = f"{int(mins_current):02}:{int(sec_current):02}"

        print(f"{self.prefix}[{u'█' * x}{('.' * (self.size - x))}] {self.current}/{self.count}"
              f" [{time_str_current}<{time_str}, {rate:.2f} it/s]", end='\r', flush=True, file=self.out)

    def close(self):
        print("\n", flush=True, file=self.out)
