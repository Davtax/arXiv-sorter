import json
import os
import shutil
import stat
from contextlib import redirect_stdout
from pathlib import Path
from subprocess import run
from threading import active_count
from time import sleep

import requests
from feedparser import FeedParserDict
from pymupdf import Rect
from pymupdf import open as pymupdf  # TODO: PyMuPDF is too heavy, consider using other library

from app.utils import Progressbar, get_urls_async

PDFFIGURES2_PATH = Path('.arXiv_sorter') / 'pdffigures2-0.0.12.jar'
PDFFIGURES2_URL = f'https://github.com/Davtax/arXiv-sorter/raw/refs/heads/main/{PDFFIGURES2_PATH.as_posix()}'


def download_pdfs(ids_entries: list[str], pdf_folder: Path, batch_size: int = 25, t_sleep: float = 1) -> None:
    """
    Download the PDFs of the entries in batches, to avoid being blocked by arXiv.
    """
    results = []
    pbar = Progressbar(len(ids_entries), prefix='Downloading PDFs')

    urls = [f'https://arxiv.org/pdf/{id_}' for id_ in ids_entries]

    previous = 0
    for i in range(0, len(ids_entries), batch_size):
        results += get_urls_async(urls[i:i + batch_size], progress_bar=False)
        sleep(t_sleep)
        pbar.update(len(results) - previous)
        previous = len(results)
    pbar.close()

    for id_entry, result in zip(ids_entries, results, strict=True):
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
    run(args, capture_output=True)


def _extract_region(id_entry: str, pdf_folder: Path, image_folder: Path, json_entry: dict, dpi: int = 300):
    # Extract region from pdf_file using json_entry
    region = json_entry['regionBoundary']
    rect = Rect(region['x1'], region['y1'], region['x2'], region['y2'])

    # Prevent muPDF from printing to stdout (restored even if the region is out of the page)
    with pymupdf(pdf_folder / f'{id_entry}.pdf') as doc, open(os.devnull, 'w') as devnull, redirect_stdout(devnull):
        page = doc[json_entry['page']]
        page.set_cropbox(rect)
        page.get_pixmap(dpi=dpi).save(image_folder / f'{id_entry}.png')


def extract_from_json(id_entry: str, json_folder: Path, pdf_folder: Path, image_folder: Path) -> bool:
    # Extract only the first figure from json_file
    # encoding = 'utf-8'
    encoding = 'iso-8859-1'

    try:
        with (json_folder / f'{id_entry}.json').open('r', encoding=encoding) as file:
            data = json.load(file)
    except FileNotFoundError:
        return False
    except (UnicodeDecodeError, json.JSONDecodeError):
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
        markdown_exists = (abstracts_dir / f'{date_dir.name}.md').exists() or (abstracts_dir / date_dir.name).is_dir()
        if date_dir.is_dir() and not markdown_exists:
            try:
                shutil.rmtree(date_dir)
            except PermissionError:
                print(f'Permission error deleting {date_dir}')


def check_java() -> bool:
    # Check if java is installed in the system
    try:
        run(['java', '-version'], capture_output=True)
        return True
    except FileNotFoundError:
        print('Java is not installed. Please install it.')
        print('Running without figure detection.')
        return False


def check_pdffigure2() -> bool:
    # Check if pdffigure2 is installed in the system, and download it otherwise
    if PDFFIGURES2_PATH.is_file():
        return True

    print('pdffigures2 is not installed. Downloading it from GitHub ...')
    try:
        response = requests.get(PDFFIGURES2_URL, timeout=60)
        response.raise_for_status()
    except requests.RequestException as error:
        print(f'Unable to download pdffigures2 ({error}). Running without figure detection.')
        return False

    PDFFIGURES2_PATH.parent.mkdir(parents=True, exist_ok=True)
    PDFFIGURES2_PATH.write_bytes(response.content)
    return True


def create_folders(*folders: Path) -> None:
    # Create folders
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)


def remove_readonly(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def get_images_pdf_scrapper(date: str, entries: list[FeedParserDict], temp_dir, abstracts_dir: Path,
                            separate_files: bool) -> list[str | None]:
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

    if not check_java() or not check_pdffigure2():
        return [None] * len(ids_entries)

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
