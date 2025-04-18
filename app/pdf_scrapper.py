import json
import os
import shutil
import sys
from subprocess import PIPE, run
from threading import active_count
from time import sleep
from typing import List, Optional, Union

import requests
from feedparser import FeedParserDict
from pymupdf import open as pymupdf, Rect  # TODO: PyMuPDF is too heavy, consider using other library

from app.utils import get_urls_async, Progressbar

ABSTRACT_FOLDER = 'abstracts'
FIGURES_FOLDER = f'{ABSTRACT_FOLDER}/figures'
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
    # encoding = 'utf-8'
    encoding = 'iso-8859-1'

    try:
        with open(f'{json_folder}/{id_entry}.json', 'r', encoding=encoding) as file:
            data = json.load(file)
    except FileNotFoundError:
        return False
    except UnicodeDecodeError:
        print(f'Error decoding {json_folder}/{id_entry}.json')
        return False

    # Sort data by page
    data = sorted(data, key=lambda x: (x['page'], x['regionBoundary']['x1'], x['regionBoundary']['y1']))

    for json_entry in data:
        if json_entry['figType'] == 'Figure':
            try:
                _extract_region(id_entry, pdf_folder, image_folder, json_entry)
                return True
            except ValueError:
                # Sometimes pdf2figures2 detects figures out of the page
                pass

    return False


def clean_previous_figures() -> None:
    # Check if the markdown file is deleted, and delete the corresponding figures
    for date in os.listdir(FIGURES_FOLDER):
        # Check if is a folder
        if os.path.isdir(f'{FIGURES_FOLDER}/{date}'):
            if f'{date}.md' not in os.listdir(ABSTRACT_FOLDER):
                try:
                    shutil.rmtree(f'{FIGURES_FOLDER}/{date}')
                except PermissionError:
                    print(f'Permission error deleting {FIGURES_FOLDER}/{date}')


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


def get_images_pdf_scrapper(date: str, entries: List[FeedParserDict], TMP_FOLDER: str) -> List[Union[str, None]]:
    if not os.path.isdir(FIGURES_FOLDER):
        os.mkdir(FIGURES_FOLDER)  # Create dir if it doesn't exist

    ids_entries = [entry.id.split('/')[-1] for entry in entries]

    pdf_folder = f'{TMP_FOLDER.name}/{date}/pdfs'
    json_folder = f'{TMP_FOLDER.name}/{date}/data'
    image_folder = f'{FIGURES_FOLDER}/{date}'

    threads_num = active_count()

    clean_previous_figures()

    # Clean image folder
    if os.path.exists(image_folder):
        shutil.rmtree(image_folder)

    create_folders(f'{TMP_FOLDER.name}/{date}', pdf_folder, json_folder, image_folder)

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

    # TODO: Check relative path between markdown file and images or work with absolute paths
    for i, figure_link in enumerate(figure_links):
        if figure_link is not None:
            figure_links[i] = '../' + figure_link  # Only accept relative paths

    return figure_links
