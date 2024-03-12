import grequests
import requests


def main():
    async_list = []
    for site in extractsites():
        action_item = grequests.get(site, hooks={'response': handleresponse})
        async_list.append(action_item)

    grequests.map(async_list)

    return async_list


def extractsites():
    return ['https://arxiv.org/html/2401.09549v3', 'https://arxiv.org/html/2309.10115v3',
            'https://arxiv.org/html/2311.03208v3', 'https://arxiv.org/html/2403.06333v1',
            'https://arxiv.org/html/2403.06522v1', 'https://arxiv.org/html/2403.06894v1',
            'https://arxiv.org/html/2403.06229v1', 'https://arxiv.org/html/2403.05497v1',
            'https://arxiv.org/html/2403.05498v1', 'https://arxiv.org/html/2403.05504v1',
            'https://arxiv.org/html/2403.05509v1', 'https://arxiv.org/html/2403.05510v1',
            'https://arxiv.org/html/2403.05515v1', 'https://arxiv.org/html/2403.05517v1',
            'https://arxiv.org/html/2403.05522v1', 'https://arxiv.org/html/2403.05528v1',
            'https://arxiv.org/html/2403.05622v1', 'https://arxiv.org/html/2403.05633v1',
            'https://arxiv.org/html/2403.05665v1', 'https://arxiv.org/html/2403.05689v1',
            'https://arxiv.org/html/2403.05691v1', 'https://arxiv.org/html/2403.05694v1',
            'https://arxiv.org/html/2403.05724v1', 'https://arxiv.org/html/2403.05729v1',
            'https://arxiv.org/html/2403.05747v1', 'https://arxiv.org/html/2403.05769v1',
            'https://arxiv.org/html/2403.05867v1', 'https://arxiv.org/html/2403.05869v1',
            'https://arxiv.org/html/2403.05872v1', 'https://arxiv.org/html/2403.05875v1',
            'https://arxiv.org/html/2403.05885v1', 'https://arxiv.org/html/2403.05889v1',
            'https://arxiv.org/html/2403.05903v1', 'https://arxiv.org/html/2403.05914v1',
            'https://arxiv.org/html/2403.05915v1', 'https://arxiv.org/html/2403.05917v1',
            'https://arxiv.org/html/2403.05945v1', 'https://arxiv.org/html/2403.05951v1',
            'https://arxiv.org/html/2403.05952v1', 'https://arxiv.org/html/2403.05953v1',
            'https://arxiv.org/html/2403.05958v1', 'https://arxiv.org/html/2403.05971v1',
            'https://arxiv.org/html/2403.05980v1', 'https://arxiv.org/html/2403.05983v1',
            'https://arxiv.org/html/2403.05990v1', 'https://arxiv.org/html/2403.05997v1',
            'https://arxiv.org/html/2403.06001v1', 'https://arxiv.org/html/2403.06005v1',
            'https://arxiv.org/html/2403.06008v1', 'https://arxiv.org/html/2403.06022v1',
            'https://arxiv.org/html/2403.06040v1', 'https://arxiv.org/html/2403.06046v1',
            'https://arxiv.org/html/2403.06049v1', 'https://arxiv.org/html/2403.06061v1',
            'https://arxiv.org/html/2403.06085v1', 'https://arxiv.org/html/2403.06118v1',
            'https://arxiv.org/html/2403.06123v1', 'https://arxiv.org/html/2403.06155v1',
            'https://arxiv.org/html/2403.06157v1', 'https://arxiv.org/html/2403.06162v1',
            'https://arxiv.org/html/2403.06165v1', 'https://arxiv.org/html/2403.06170v1',
            'https://arxiv.org/html/2403.06175v1', 'https://arxiv.org/html/2403.06195v1',
            'https://arxiv.org/html/2403.06212v1', 'https://arxiv.org/html/2403.06215v1',
            'https://arxiv.org/html/2403.06226v1', 'https://arxiv.org/html/2403.06231v1',
            'https://arxiv.org/html/2403.06232v1', 'https://arxiv.org/html/2403.06256v1',
            'https://arxiv.org/html/2403.06271v1', 'https://arxiv.org/html/2403.06274v1',
            'https://arxiv.org/html/2403.06283v1', 'https://arxiv.org/html/2403.06296v1',
            'https://arxiv.org/html/2403.06304v1', 'https://arxiv.org/html/2403.06305v1',
            'https://arxiv.org/html/2403.06325v1', 'https://arxiv.org/html/2403.06329v1',
            'https://arxiv.org/html/2403.06359v1', 'https://arxiv.org/html/2403.06373v1',
            'https://arxiv.org/html/2403.06379v1', 'https://arxiv.org/html/2403.06380v1',
            'https://arxiv.org/html/2403.06386v1', 'https://arxiv.org/html/2403.06389v1',
            'https://arxiv.org/html/2403.06426v1', 'https://arxiv.org/html/2403.06442v1',
            'https://arxiv.org/html/2403.06446v1', 'https://arxiv.org/html/2403.06450v1',
            'https://arxiv.org/html/2403.06451v1', 'https://arxiv.org/html/2403.06472v1',
            'https://arxiv.org/html/2403.06476v1', 'https://arxiv.org/html/2403.06481v1',
            'https://arxiv.org/html/2403.06500v1', 'https://arxiv.org/html/2403.06521v1',
            'https://arxiv.org/html/2403.06531v1', 'https://arxiv.org/html/2403.06539v1',
            'https://arxiv.org/html/2403.06549v1', 'https://arxiv.org/html/2403.06553v1',
            'https://arxiv.org/html/2403.06556v1', 'https://arxiv.org/html/2403.06565v1',
            'https://arxiv.org/html/2403.06598v1', 'https://arxiv.org/html/2403.06603v1',
            'https://arxiv.org/html/2403.06604v1', 'https://arxiv.org/html/2403.06618v1',
            'https://arxiv.org/html/2403.06627v1', 'https://arxiv.org/html/2403.06630v1',
            'https://arxiv.org/html/2403.06649v1', 'https://arxiv.org/html/2403.06650v1',
            'https://arxiv.org/html/2403.06655v1', 'https://arxiv.org/html/2403.06666v1',
            'https://arxiv.org/html/2403.06673v1', 'https://arxiv.org/html/2403.06709v1',
            'https://arxiv.org/html/2403.06713v1', 'https://arxiv.org/html/2403.06740v1',
            'https://arxiv.org/html/2403.06778v1', 'https://arxiv.org/html/2403.06795v1',
            'https://arxiv.org/html/2403.06799v1', 'https://arxiv.org/html/2403.06822v1',
            'https://arxiv.org/html/2403.06824v1', 'https://arxiv.org/html/2403.06825v1',
            'https://arxiv.org/html/2403.06827v1', 'https://arxiv.org/html/2403.06848v1',
            'https://arxiv.org/html/2403.06861v1', 'https://arxiv.org/html/2403.06875v1',
            'https://arxiv.org/html/2403.06878v1', 'https://arxiv.org/html/2403.06882v1',
            'https://arxiv.org/html/2403.06909v1', 'https://arxiv.org/html/2403.06918v1',
            'https://arxiv.org/html/2403.06934v1', 'https://arxiv.org/html/2403.06944v1',
            'https://arxiv.org/html/2403.06949v1', 'https://arxiv.org/html/2403.06955v1',
            'https://arxiv.org/html/2403.06964v1']


def handleresponse(response, **kwargs):
    fp = response.text
    index_f = fp.find('.png')
    index_0 = fp.rfind('src="', 0, index_f + 4)

    if index_0 != -1 and index_f != -1:
        print(fp[index_0 + 5:index_f + 4])


if __name__ == '__main__':
    result = main()
