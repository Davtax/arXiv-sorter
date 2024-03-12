from time import sleep
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


def get_image_urls(ids: list[str]) -> list[str]:
    async_list = []
    urls = [f'https://arxiv.org/html/{id_}' for id_ in ids]

    for site in urls:
        action_item = grequests.get(site)
        async_list.append(action_item)

    results = grequests.map(async_list)

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
    fp = response.text
    index_f = fp.find('.png')
    index_0 = fp.rfind('src="', 0, index_f + 4)

    if index_0 == -1 or index_f == -1:
        return ''

    return fp[index_0 + 5:index_f + 4]
