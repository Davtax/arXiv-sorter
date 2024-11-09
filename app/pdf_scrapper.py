import json
import os
import shutil
import sys
from subprocess import PIPE, run
from threading import activeCount
from time import sleep
from typing import List, Optional, Union

import requests
from feedparser import FeedParserDict
from pymupdf import open as pymupdf, Rect  # TODO: PyMuPDF is too heavy, consider using other library

from app.utils import get_urls_async, Progressbar

ABSTRACT_FOLDER = 'abstracts'
TMP_FOLDER = f'{ABSTRACT_FOLDER}/.tmp'
PDFFIGURES2_PATH = '.arXiv_sorter/pdffigures2-0.0.12.jar'
PDFFIGURES2_URL = f'https://github.com/Davtax/arXiv-sorter/raw/refs/heads/main/{PDFFIGURES2_PATH}'


def download_pdfs(ids_entries: List[str], pdf_folder: str, batch_size: Optional[int] = 25,
                  t_sleep: Optional[int] = 1) -> None:
    # Batch async version
    results = []
    pbar = Progressbar(len(ids_entries), prefix='Downloading PDFs')

    urls = [f'https://arxiv.org/pdf/{id_}' for id_ in ids_entries]

    previous = 0
    for i in range(0, len(ids_entries), batch_size):
        results += get_urls_async(urls[i:i + batch_size], progres_bar=False)
        sleep(t_sleep)
        pbar.update(len(results) - previous)
        previous = len(results)
    pbar.close()

    for id_entry, result in zip(ids_entries, results):
        if result is None:
            print(f'Error in {id_entry}')
            continue
        elif result.status_code == 403:
            print(f'403 error in {id_entry}')
            continue

        with open(f'{pdf_folder}/{id_entry}.pdf', 'wb') as f:
            f.write(result.content)


def detect_figure(pdf_folder: str, json_folder: str, threads_num: int) -> None:
    # Detect figures from from pdfs in pdf_folder, and save .json files in json_folder
    print('Detecting figures in PDF files ...')
    args = f'java -jar {PDFFIGURES2_PATH} {pdf_folder} -e -t {threads_num} -d {json_folder}/ -q'
    args = args.split()
    run(args, stdout=PIPE, stderr=PIPE)


def _extract_region(id_entry: str, pdf_folder: str, image_folder: str, json_entry: dict, dpi: Optional[int] = 300):
    # Extract region from pdf_file using json_entry
    doc = pymupdf(f'{pdf_folder}/{id_entry}.pdf')

    region = json_entry['regionBoundary']
    x1, x2, y1, y2 = region['x1'], region['x2'], region['y1'], region['y2']

    # Select page to crop
    page = doc[json_entry['page']]

    # Prevent muPDF from printing to stdout
    old_stdout = sys.stdout  # backup current stdout
    sys.stdout = open(os.devnull, "w")

    page.set_cropbox(Rect(x1, y1, x2, y2))
    page.get_pixmap(dpi=dpi).save(f'{image_folder}/{id_entry}.png')

    sys.stdout = old_stdout

    doc.close()


def extract_from_json(id_entry: str, json_folder: str, pdf_folder: str, image_folder: str) -> bool:
    # Extract only the first figure from json_file
    try:
        with open(f'{json_folder}/{id_entry}.json', 'r', encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        return False

    # Sort data by page
    data = sorted(data, key=lambda x: (x['page'], x['regionBoundary']['x1'], x['regionBoundary']['y1']))

    for json_entry in data:
        if json_entry['figType'] == 'Figure':
            _extract_region(id_entry, pdf_folder, image_folder, json_entry)
            return True

    return False


def clean_previous_figures() -> None:
    # Check if the markdown file is deleted, and delete the corresponding figures
    abstracts_folder = 'abstracts'

    for image_folder in os.listdir(TMP_FOLDER):
        # Check if is a folder
        if os.path.isdir(f'{TMP_FOLDER}/{image_folder}'):
            if f'{image_folder}.md' not in os.listdir(abstracts_folder):
                shutil.rmtree(f'{TMP_FOLDER}/{image_folder}')


def check_java() -> bool:
    # Check if java is installed in the system
    try:
        run(['java', '-version'], stdout=PIPE, stderr=PIPE)
        return True
    except FileNotFoundError:
        print('Java is not installed. Please install it.')
        print('Running without figure detection.')
        return False


def check_pdffigure2():
    # Check if pdffigure2 is installed in the system
    if not os.path.isfile(PDFFIGURES2_PATH):
        print('pdffigures2 is not installed. Downloading it from GitHub ...')

        # Download the file
        response = requests.get(PDFFIGURES2_URL)
        with open(PDFFIGURES2_PATH, 'wb') as f:
            f.write(response.content)


def create_folders(*folders: str) -> None:
    # Create folders
    for folder in folders:
        os.makedirs(folder)


def get_images_pdf_scrapper(date: str, entries: List[FeedParserDict]) -> List[Union[str, None]]:
    # Check if TMP_FOLDER exists
    if not os.path.exists(TMP_FOLDER):
        os.mkdir(TMP_FOLDER)

    ids_entries = [entry.id.split('/')[-1] for entry in entries]

    pdf_folder = f'{TMP_FOLDER}/{date}/pdfs'
    json_folder = f'{TMP_FOLDER}/{date}/data'
    image_folder = f'{TMP_FOLDER}/{date}/figures'

    threads_num = activeCount()

    # Remove folders if they exist
    if os.path.isdir(f'{TMP_FOLDER}/{date}'):
        shutil.rmtree(f'{TMP_FOLDER}/{date}')

    clean_previous_figures()

    create_folders(f'{TMP_FOLDER}/{date}', pdf_folder, json_folder, image_folder)

    if not check_java():
        return [None] * len(ids_entries)
    check_pdffigure2()

    # Download pdfs
    download_pdfs(ids_entries, pdf_folder)

    # Detect figures from pdfs
    detect_figure(pdf_folder, json_folder, threads_num)

    # Extract figures from json files
    figure_links = []
    pbar = Progressbar(len(ids_entries), prefix='Extracting figures')
    for id_entry in ids_entries:
        if extract_from_json(id_entry, json_folder, pdf_folder, image_folder):
            figure_links.append(f'{image_folder}/{id_entry}.png')
        else:
            figure_links.append(None)
        pbar.update(1)
    pbar.close()

    # Clean up temporary folders
    shutil.rmtree(pdf_folder)
    shutil.rmtree(json_folder)

    # TODO: Check relative path between markdown file and images or work with absolute paths
    for i, figure_link in enumerate(figure_links):
        if figure_link is not None:
            figure_links[i] = '../' + figure_link

    return figure_links
