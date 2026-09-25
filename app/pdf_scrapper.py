import json
import os
import shutil
import sys
from subprocess import PIPE, run
from threading import active_count
from time import sleep
from pathlib import Path
from typing import List, Optional, Union
import stat

import requests
from feedparser import FeedParserDict
from pymupdf import open as pymupdf, Rect  # TODO: PyMuPDF is too heavy, consider using other library

from app.utils import get_urls_async, Progressbar

PDFFIGURES2_PATH = Path('.arXiv_sorter') / 'pdffigures2-0.0.12.jar'
PDFFIGURES2_URL = f'https://github.com/Davtax/arXiv-sorter/raw/refs/heads/main/{PDFFIGURES2_PATH.as_posix()}'


def download_pdfs(ids_entries: List[str], pdf_folder: Path, batch_size: Optional[int] = 25,
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

        with (pdf_folder / f'{id_entry}.pdf').open('wb') as f:
            f.write(result.content)


def detect_figure(pdf_folder: Path, json_folder: Path, threads_num: int) -> None:
    # Detect figures from pdfs in pdf_folder, and save .json files in json_folder
    print('Detecting figures in PDF files ...')
    args = ['java', '-jar', PDFFIGURES2_PATH, pdf_folder, '-e', '-t', str(threads_num), '-d', json_folder, '-q']
    run(args, stdout=PIPE, stderr=PIPE)


def _extract_region(id_entry: str, pdf_folder: Path, image_folder: Path, json_entry: dict, dpi: Optional[int] = 300):
    # Extract region from pdf_file using json_entry
    doc = pymupdf(pdf_folder / f'{id_entry}.pdf')

    region = json_entry['regionBoundary']
    x1, x2, y1, y2 = region['x1'], region['x2'], region['y1'], region['y2']

    # Select page to crop
    page = doc[json_entry['page']]

    # Prevent muPDF from printing to stdout
    old_stdout = sys.stdout  # backup current stdout
    sys.stdout = open(os.devnull, "w")

    page.set_cropbox(Rect(x1, y1, x2, y2))
    page.get_pixmap(dpi=dpi).save(image_folder / f'{id_entry}.png')

    sys.stdout = old_stdout

    doc.close()


def extract_from_json(id_entry: str, json_folder: Path, pdf_folder: Path, image_folder: Path) -> bool:
    # Extract only the first figure from json_file
    # encoding = 'utf-8'
    encoding = 'iso-8859-1'

    try:
        with (json_folder / f'{id_entry}.json').open('r', encoding=encoding) as file:
            data = json.load(file)
    except FileNotFoundError:
        return False
    except UnicodeDecodeError:
        print(f'Error decoding {json_folder / f"{id_entry}.json"}')
        return False
    except json.decoder.JSONDecodeError:
        print(f'Error decoding {json_folder / f"{id_entry}.json"}')
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


def clean_previous_figures(abstracts_dir: Path) -> None:
    # Check if the markdown file is deleted, and delete the corresponding figures
    figures_dir = abstracts_dir / 'figures'
    for date_dir in figures_dir.iterdir():
        if date_dir.is_dir():
            if not (abstracts_dir / f'{date_dir.name}.md').exists() and not (abstracts_dir / date_dir.name).is_dir():
                try:
                    shutil.rmtree(date_dir)
                except PermissionError:
                    print(f'Permission error deleting {date_dir}')


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
    if not PDFFIGURES2_PATH.is_file():
        print('pdffigures2 is not installed. Downloading it from GitHub ...')

        # Download the file
        response = requests.get(PDFFIGURES2_URL)
        with PDFFIGURES2_PATH.open('wb') as f:
            f.write(response.content)


def create_folders(*folders: Path) -> None:
    # Create folders
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)


def remove_readonly(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def get_images_pdf_scrapper(date: str, entries: List[FeedParserDict], temp_dir, abstracts_dir: Path,
                            separate_files: bool) -> List[Union[str, None]]:
    figures_dir = abstracts_dir / 'figures'
    figures_dir.mkdir(parents=True, exist_ok=True)

    ids_entries = [entry.id.split('/')[-1] for entry in entries]

    temporary_date_dir = Path(temp_dir.name) / date
    pdf_folder = temporary_date_dir / 'pdfs'
    json_folder = temporary_date_dir / 'data'
    image_folder = figures_dir / date

    threads_num = active_count()

    clean_previous_figures(abstracts_dir)

    # Clean image folder
    if image_folder.exists():
        shutil.rmtree(image_folder, onexc=remove_readonly)

    create_folders(temporary_date_dir, pdf_folder, json_folder, image_folder)

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
            image_path = image_folder / f'{id_entry}.png'
            if separate_files:
                figure_links.append((Path('..') / image_path.relative_to(abstracts_dir)).as_posix())
            else:
                figure_links.append(image_path.relative_to(abstracts_dir).as_posix())
        else:
            figure_links.append(None)
        pbar.update(1)
    pbar.close()

    return figure_links
