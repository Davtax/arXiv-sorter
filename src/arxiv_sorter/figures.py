import json
import os
import shutil
import stat
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from contextlib import redirect_stdout
from pathlib import Path
from subprocess import DEVNULL, Popen
from time import sleep

import requests
from feedparser import FeedParserDict
from pymupdf import Rect
from pymupdf import open as pymupdf  # TODO: PyMuPDF is too heavy, consider using other library

from arxiv_sorter import console
from arxiv_sorter.console import Progressbar
from arxiv_sorter.java_runtime import find_java
from arxiv_sorter.network import get_urls_async
from arxiv_sorter.system import NO_WINDOW, config_dir

PDFFIGURES2_JAR = 'pdffigures2-0.0.12.jar'
# Kept in the configuration folder (next to the GUI settings), so it persists wherever the program is run from
PDFFIGURES2_PATH = config_dir() / PDFFIGURES2_JAR
# Location used by previous versions, next to the program (relative to the working directory); also where the
# repository keeps it
LEGACY_PDFFIGURES2_PATH = Path('.arXiv_sorter') / PDFFIGURES2_JAR
PDFFIGURES2_URL = f'https://github.com/Davtax/arXiv-sorter/raw/refs/heads/main/.arXiv_sorter/{PDFFIGURES2_JAR}'
# Maximum of figures detected in a run, set by the CI so its test runs do not download every PDF from arXiv
MAX_FIGURES_ENV_VAR = 'ARXIV_SORTER_MAX_FIGURES'


def max_figures() -> int | None:
    """
    Maximum of figures detected in a run, given by the environment variable ARXIV_SORTER_MAX_FIGURES (None if it is not
    set, or not a number: no limit).
    """
    try:
        return max(int(os.environ[MAX_FIGURES_ENV_VAR]), 0)
    except (KeyError, ValueError):
        return None


def download_pdfs(ids_entries: list[str], pdf_folder: Path, batch_size: int = 25, t_sleep: float = 1) -> None:
    """
    Download the PDFs of the entries in batches, to avoid being blocked by arXiv.
    """
    results = []
    pbar = Progressbar(len(ids_entries), prefix='Downloading PDFs', icon='📥')

    urls = [f'https://arxiv.org/pdf/{id_}' for id_ in ids_entries]

    previous = 0
    for i in range(0, len(ids_entries), batch_size):
        results += get_urls_async(urls[i:i + batch_size], progress_bar=False)
        sleep(t_sleep)
        pbar.update(len(results) - previous)
        previous = len(results)
    pbar.close()

    failed, refused = [], []
    for id_entry, result in zip(ids_entries, results, strict=True):
        if result is None:
            failed.append(id_entry)
            continue
        elif result.status_code == 403:
            refused.append(id_entry)
            continue

        with (pdf_folder / f'{id_entry}.pdf').open('wb') as f:
            f.write(result.content)

    if failed:
        console.warning(f'{len(failed)} PDFs could not be downloaded, they will have no figure: {", ".join(failed)}')
    if refused:
        console.warning(f'arXiv refused to send {len(refused)} PDFs (error 403, usually after too many downloads), '
                        f'they will have no figure: {", ".join(refused)}')


def detect_figure(pdf_folder: Path,
                  json_folder: Path,
                  threads: int,
                  java: str | os.PathLike[str] = 'java',
                  t_poll: float = 0.5
                  ) -> None:
    """
    Detect the figures of the PDFs with pdffigures2, run by the given java executable, which saves a JSON file per PDF
    inside json_folder.
    pdffigures2 runs in the background, while the JSON files already written are counted to show the progress.
    """
    json_folder.mkdir(parents=True, exist_ok=True)
    n_pdfs = sum(1 for _ in pdf_folder.glob('*.pdf'))

    args: list[str | os.PathLike[str]] = [java, '-jar', PDFFIGURES2_PATH, pdf_folder, '-e', '-t', str(threads), '-d',
                                          str(json_folder) + os.sep, '-q']
    # The output is not read, so it is discarded instead of piped (a full pipe would block pdffigures2)
    process = Popen(args, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, creationflags=NO_WINDOW)

    if n_pdfs == 0:
        process.wait()
        return

    pbar = Progressbar(n_pdfs, prefix='Detecting figures', icon='🔍')
    n_done = 0
    while process.poll() is None:
        sleep(t_poll)
        n_json = min(sum(1 for _ in json_folder.glob('*.json')), n_pdfs)
        if n_json > n_done:
            pbar.update(n_json - n_done)
            n_done = n_json

    if n_done < n_pdfs:  # PDFs without a JSON file (e.g. not readable) are also finished
        pbar.update(n_pdfs - n_done)
    pbar.close()


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
    """
    Save the first figure detected in the PDF of the entry as an image. False if it has none.
    """
    found, detail = _first_figure(id_entry, json_folder, pdf_folder, image_folder)
    if detail:
        console.detail(detail)
    return found


def _first_figure(id_entry: str, json_folder: Path, pdf_folder: Path, image_folder: Path) -> tuple[bool, str]:
    """
    Body of extract_from_json, which also runs in other processes: instead of printing, it returns whether the figure
    was saved, and a detail to show (the other processes have neither the log file nor the --verbose option).
    """
    # encoding = 'utf-8'
    encoding = 'iso-8859-1'

    try:
        with (json_folder / f'{id_entry}.json').open('r', encoding=encoding) as file:
            data = json.load(file)
    except FileNotFoundError:
        return False, ''
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, f'Unable to read the figures detected in {id_entry} ({json_folder / f"{id_entry}.json"})'

    # Sort data by page
    data = sorted(data, key=lambda x: (x['page'], x['regionBoundary']['x1'], x['regionBoundary']['y1']))

    for json_entry in data:
        if json_entry['figType'] == 'Figure':
            try:
                _extract_region(id_entry, pdf_folder, image_folder, json_entry)
                return True, ''
            except ValueError:
                # Sometimes pdf2figures2 detects figures out of the page
                pass

    return False, ''


def extract_all(ids_entries: list[str], json_folder: Path, pdf_folder: Path, image_folder: Path, threads: int = 1) -> \
list[bool]:
    """
    Save the first figure of each entry, rendering several PDFs at the same time with the given number of processes
    (PyMuPDF does not support threads, and would hold the GIL). Returns whether each entry got a figure.
    """
    found = [False] * len(ids_entries)
    workers = min(threads, len(ids_entries))
    pbar = Progressbar(len(ids_entries), prefix='Extracting figures', icon='🎨')

    if workers <= 1:  # Starting other processes takes longer than extracting a few figures
        for i, id_entry in enumerate(ids_entries):
            found[i] = extract_from_json(id_entry, json_folder, pdf_folder, image_folder)
            pbar.update(1)
        pbar.close()
        return found

    with ProcessPoolExecutor(workers) as pool:
        futures = {pool.submit(_first_figure, id_entry, json_folder, pdf_folder, image_folder): i for i, id_entry in
                   enumerate(ids_entries)}
        try:
            for future in as_completed(futures):
                found[futures[future]], detail = future.result()
                if detail:
                    console.detail(detail)
                pbar.update(1)
        except BrokenProcessPool:  # A process crashed, e.g. rendering a malformed PDF
            missing = [ids_entries[i] for future, i in futures.items() if
                       not future.done() or future.exception() is not None]
            console.warning(f'The extraction of the figures stopped unexpectedly, {len(missing)} entries have no '
                            f'figure: {", ".join(missing)}')
    pbar.close()
    return found


def clean_previous_figures(abstracts_dir: Path) -> None:
    # Check if the markdown file is deleted, and delete the corresponding figures
    figures_dir = abstracts_dir / 'figures'
    for date_dir in figures_dir.iterdir():
        markdown_exists = (abstracts_dir / f'{date_dir.name}.md').exists() or (abstracts_dir / date_dir.name).is_dir()
        if date_dir.is_dir() and not markdown_exists:
            remove_folder(date_dir)


def remove_folder(folder: Path, retries: int = 3, t_sleep: float = 1) -> bool:
    """
    Remove the folder, retrying since it can be locked for a moment (e.g. by the antivirus or a syncing cloud drive).
    """
    for attempt in range(retries + 1):
        try:
            shutil.rmtree(folder, onexc=remove_readonly)
            return True
        except FileNotFoundError:
            return True
        except PermissionError:
            if attempt < retries:
                sleep(t_sleep)

    console.warning(f'Permission error deleting {folder} (it may be open in another program), it will be retried in '
                    'the next run')
    return False


def check_pdffigure2() -> bool:
    """
    Check if pdffigures2 is available in the configuration folder. Otherwise, it is copied from the location used by
    previous versions, or downloaded from GitHub (only the first time, it is kept for the next runs).
    """
    if PDFFIGURES2_PATH.is_file():
        return True

    # Written to a temporary file first, so an interrupted copy or download does not leave a broken jar behind
    partial_path = PDFFIGURES2_PATH.with_suffix('.part')

    try:
        PDFFIGURES2_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LEGACY_PDFFIGURES2_PATH.is_file():
            shutil.copyfile(LEGACY_PDFFIGURES2_PATH, partial_path)
            partial_path.replace(PDFFIGURES2_PATH)
            console.success(f'pdffigures2 copied from {LEGACY_PDFFIGURES2_PATH.resolve()} to {PDFFIGURES2_PATH}')
            return True
    except OSError as error:
        console.warning(f'Unable to save pdffigures2 in {PDFFIGURES2_PATH.parent} ({error}). Running without figure '
                        'detection.')
        return False

    console.info('Downloading pdffigures2 (34 MB), the tool that detects the figures. It is only needed the first '
                 'time …', icon='📦')
    try:
        response = requests.get(PDFFIGURES2_URL, timeout=60)
        response.raise_for_status()
        partial_path.write_bytes(response.content)
        partial_path.replace(PDFFIGURES2_PATH)
    except (requests.RequestException, OSError) as error:
        console.warning(f'Unable to download pdffigures2 ({error}). Running without figure detection.')
        return False

    console.success(f'pdffigures2 saved in {PDFFIGURES2_PATH}')
    return True


def create_folders(*folders: Path) -> None:
    # Create folders
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)


def remove_readonly(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def extract_figures(date: str,
                    entries: list[FeedParserDict],
                    temp_dir,
                    abstracts_dir: Path,
                    separate_files: bool,
                    threads: int = 1, ) -> list[str | None]:
    """
    Download the PDFs of the entries and extract their first figure, detected by pdffigures2 with the given number of
    threads and saved as images by as many processes (each one processes a PDF at a time, so more threads are faster
    but use more memory).
    Returns the link to the figure of each entry, relative to the abstracts folder (None if no figure was found).
    """
    figures_dir = abstracts_dir / 'figures'
    figures_dir.mkdir(parents=True, exist_ok=True)

    ids_entries = [entry.id.split('/')[-1] for entry in entries]

    temporary_date_dir = Path(temp_dir.name) / date
    pdf_folder = temporary_date_dir / 'pdfs'
    json_folder = temporary_date_dir / 'data'
    image_folder = figures_dir / date

    clean_previous_figures(abstracts_dir)

    # Clean image folder
    if image_folder.exists():
        remove_folder(image_folder)

    create_folders(temporary_date_dir, pdf_folder, json_folder, image_folder)

    java = find_java()
    if java is None or not check_pdffigure2():
        return [None] * len(ids_entries)

    # Download pdfs
    download_pdfs(ids_entries, pdf_folder)

    # Detect figures from pdfs
    detect_figure(pdf_folder, json_folder, threads, java)

    # Extract figures from json files, with as many processes as threads detect them
    figure_links: list[str | None] = []
    found = extract_all(ids_entries, json_folder, pdf_folder, image_folder, threads)
    for id_entry, has_figure in zip(ids_entries, found, strict=True):
        if has_figure:
            image_path = image_folder / f'{id_entry}.png'
            if separate_files:
                figure_links.append((Path('..') / image_path.relative_to(abstracts_dir)).as_posix())
            else:
                figure_links.append(image_path.relative_to(abstracts_dir).as_posix())
        else:
            figure_links.append(None)

    n_figures = sum(link is not None for link in figure_links)
    console.info(f'Figures found for {n_figures} of the {len(ids_entries)} new entries', icon='🎨')
    return figure_links
