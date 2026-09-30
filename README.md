[![GitHub version](https://badge.fury.io/gh/Davtax%2FarXiv-sorter.svg)](https://github.com/Davtax/arXiv-sorter/releases/latest)

# arXiv-sorter

Sort the daily arXiv mail list by user keywords, and output the manuscripts in a nice markdown.
The program is written in Python and compiled into a binary file using [PyInstaller](https://www.pyinstaller.org/).

The output file is a markdown file, which is intended to be used with the [Obsidian](https://obsidian.md/) note-taking
app.
The program creates a file for each mailing list, with the named `YYYY-MM-DD.md`, where `YYYY-MM-DD` is the date of the
mail.
The markdown file is inside the abstracts folder, created in the same directory as the binary file.

In the markdown file, each entry for the manuscript contains the title, authors list, abstract, the first figure of the
manuscript, a link to the manuscript, and the date of submission.
The user can specify keywords to search for in the manuscript's title, abstract, and authors list.
If the manuscript contains the keywords, this manuscript will be sorted at the top of the markdown file.
Furthermore, the matching keywords will be highlighted in the title and abstract of the manuscript.
The color code for the highlighting is the following:

- $\color{orange}\textsf{Orange}$ for the title
- $\color{green}\textsf{Green}$ for the authors
- $\color{red}\textsf{Red}$ for the abstract

Below the sorted manuscripts, the program will list all the manuscripts that do not contain the keywords, sorted by the
date of submission.
The number close to the title is the number of total manuscripts on the mailing list, excluding the ones that have been
updated (not new), and does not contain any keywords.
Those manuscripts are located at the bottom of the markdown file, and no images are included in the markdown file, to
speed up the web scraping process.
Usually, those manuscripts are not interesting to the user.

When reading the markdown file in Obsidian, make sure to bee in the preview mode, and not in the edit mode.

The images included in the markdown file are obtained via web scraping from the experimental
feature [arXiv HTML](https://info.arxiv.org/about/accessible_HTML.html).
However, not all manuscripts are automatically converted to HTML, and the program will not be able to extract the
image.

> [!IMPORTANT]  
> Since the program relies on the name of the markdown file to search for the latest file, do not rename the markdown
> files.

## Usage

1. (Only the first time) Install Obsidian, and configure a new Obsidian vault (or use the default one).
2. Download the zip file of the command line program for your system from the
   [release page](https://github.com/Davtax/arXiv-sorter/releases): `arXiv-sorter-CLI-Windows.zip`,
   `arXiv-sorter-CLI-macOS.zip` or `arXiv-sorter-CLI-Ubuntu.zip` (or the graphical interface, see
   [Graphical interface](#graphical-interface)).
3. Extract the zip file.
4. Place the binary file in the directory where you want to save the output file.
5. (Only the first time) Create the keyword files in the same directory as the binary file.
   The keyword files should be named `authors.txt`, `categories.txt`, and `keywords.txt`.
   The content of the file should be the keywords you want to search for, one keyword per line.
   If the program is run without the keyword files, the program will create the empty files.
6. Run the binary files.
   The program will search for the latest file in the `abstracts` folder, and output the markdown files between that
   date and the current date.

The final directory tree should look (if using default paths) something like:

```bash
├── arXiv-sorter
│   ├── .obsidian
│   │   ├── snippets
│   │   │   └── arXiv-sorter.css  
│   ├── abstracts
│   │   ├── YYYYMMDD(1).md
│   │   ├── YYYYMMDD(2).md
│   │   └── YYYYMMDD(3).md
│   ├── arXiv-sorter-CLI-*
│   ├── authors.txt
│   ├── categories.txt
└── └── keywords.txt

```

> [!NOTE]  
> Some antivirus programs may block the execution of the binary file.
> In this case, you can add the binary file to the exception list of the antivirus program.
> If you are using Windows, you can run the binary file as an administrator.

> [!NOTE]  
> On Mac, when downloading a new version, an unidentified developer warning pops up.
> To solve that, open the program once, then go to System Settings -> Privacy & Security and click Open Anyway
> (on macOS 14 and older, Right click -> Open -> Open also works), or run
> `xattr -d com.apple.quarantine arXiv-sorter-CLI-macOS` in its folder.
> Once solved, the message will disappear.

> [!WARNING]  
> Sometimes the arXiv API does not respond as usual.
> The program retries the requests, and if a mailing list has no submissions, it looks for the previous one, up to 10
> requests. After that it stops with a warning: check the categories in `categories.txt`, or try again in a few
> minutes.

Each run writes a log file with all the messages, including the details only shown with `--verbose`, in the `logs`
folder next to the settings (see [Graphical interface](#graphical-interface)).
The last 30 are kept, and they are useful to report a problem.

## Keywords

In each line of the keyword files, you can specify the keywords you want to search for (logic OR).
The program will search for the keywords in the title, abstract, and authors of the manuscript.
The program is case-insensitive, and the keywords can be written in any case.
The search is based on the module [re](https://docs.python.org/3/library/re.html), so you can use regular expressions to
search for the keywords, e.g., `spin[- ]orbit` will search for both `spin-orbit` and `spin orbit`.
A good website to test regular expressions is [regex101](https://regex101.com/).
You can combine multiple keywords in the same line using the `&` character, with no spaces between the keywords, e.g.,
`keyword1&keyword2`.
The program will search for the manuscripts that contain all the keywords at the same time (logical AND).
You can combine regular expressions with the `&` character, e.g., `spin[- ]orbit&spin qubit` will search for manuscripts
that contain both (`spin-orbit` or `spin orbit`) and `spin qubit` at the same time.
Finally, you can use the `#` character at the beginning of the line to comment it out so the program will ignore that
line.

Before requesting arXiv, the program checks the search files: an invalid regular expression (e.g. `spin[ qubit`) or an
empty term next to `&` (which would match every manuscript) stops the run, with the file and line of the mistake.
Lines of `categories.txt` that do not look like arXiv categories are reported as warnings.
In the graphical interface, the files can be edited with these checks while typing, and with a preview of the
manuscripts of the latest mailing list that would match (*Edit* next to the number of keywords, authors and categories).

After the program is run, the authors inside the `authors.txt` file will be sorted alphabetically by the surname.
When searching for author, the program automatically normalize the author names provided by the user, to use unicode
characters and remove accents.
Furthermore, the program perform a case-insensitive search for the author names.
For example, D. Fernández becomes D. Fernandez, and A. Löwdin becomes A. Lowdin.
After searching for the authors, the program recover the original names format.
Furthermore, the program search only for full matches by enclosing the provided author names with `\b` at the beginning
and the end of the name, so `Ares` will not match Manzanares.

I recommend to use just the last name of the author, to avoid false negatives, since sometimes the author names (David
Fernández) are abbreviated in the arXiv mailing list (D. Fernández).
The best solution is to use just the first letter of the first name and the last name, together with regular expressions
in between, e.g., `M[^,]* +Ares` will match M. Ares, Maria Ares, M. N. Ares, but not Manzanares or D. Ares, or the string
(M. Perez, J. Zurita, N. Ares).

A list of all possible arXiv categories can be found [here](https://arxiv.org/category_taxonomy).
If you are interested in all the groups of a category, just write the category letters in the `categories.txt` file.
If the same manuscript is in multiple categories, the program will print that manuscript just once.
Cross-listed manuscripts are also printed in the markdown file.

## CSS snippets

The program can make use of the CSS snippets to format the markdown file inside Obsidian.
The CSS snippets are located in the [snippets](https://github.com/Davtax/arXiv-sorter/tree/main/snippets) folder.
To install the CSS snippets, copy the content of the CSS snippets to the `.obsidian/snippets` folder in the home
directory.
Then, open the Obsidian app, and enable the CSS snippets in the Settings/Appearance/CSS snippets option.

This option is purely stylistic, and it is not necessary to run the program.
CSS files for both light and dark mode are provided.
In the dark mode, the colors are inverted, so the highlighting is still visible.

## Figures detection
By default, the program will download the .PDF file of the manuscript from arXiv, and extract the first figure.
This is saved as a .PNG file in a local folder, and linked in the markdown file.
If the markdown file is deleted, the next execution of the program will clean up the local folder with the figures.
The detection of the figures is done via the [PDFFigures2](https://github.com/allenai/pdffigures2) library.
PDFFigures2 is downloaded from this repository the first time (34 MB), and kept in the configuration folder of
arXiv-sorter (the same folder as the settings of the graphical interface, see below), so it persists when the program
is moved or updated.
PDFFigures2 runs on Java, which does not need to be installed: if it is not, a Java runtime
([Eclipse Temurin](https://adoptium.net) 21, about 50 MB) is downloaded the first time and kept in the same folder.
Sometimes, PFFigures2 is not able to detect the figure, or misunderstand some text as a figure.
Finally, the extraction of the figure to a .PNG file is done via [PyMuPDF](https://github.com/pymupdf/PyMuPDF).
After the extraction, the .PDF files saved in local are deleted.
The process of downloading the .PDF file, detecting and extracting the figure is time-consuming,
so it is only done for new manuscripts, and those new versions of the manuscripts that contain the keywords.
However, it can be entirely disabled with the `--image` flag (see below).

> [!WARNING]  
> The program will download the .PDF files directly from the arXiv website.
> There is a waiting time between each download to avoid being blocked by the arXiv server.
> However, sometimes the server will block the IP address.
> In this case, you will not be able to enter the arXiv website for a few hours.
> Use this program under your own responsibility.

## Optional arguments

The messages in the terminal use colors and emojis when the terminal supports them.
The old Windows console shows emojis as empty boxes, so there they are left out (Windows Terminal shows them).
Set the environment variable `ARXIV_SORTER_PLAIN=1` to print plain text, or `NO_COLOR=1` to only remove the colors.

When running the program from the terminal, you can use the following optional arguments:

- `--help` or `-h`: Show the help message and exit.
- `--verbose` or `-v`: Print the output to the terminal.
- `--directory` or `-d`: Specify the directory where the keyword files are located.
  The default value is the current directory (`./`).
- `--abstracts` or `-a`: Specify the directory where the abstracts are located.
  The default value is the `abstracts` folder in the current directory (`/abstracts`).
- `--final` or `-f`: Remove the final time stamp from the markdown file.
- `--update` or `-u`: If there is a new version of the program in GitHub, ask to download it and replace the binary
  with it (then run the program again). Without it, new versions are only announced.
- `--exit` or `-e`: Exit the program without the need to press `Enter` at the end.
  This option is useful if you want to run the program in a cron job, and you don't want to keep the terminal open.
- `--separate` or `-s`: Create a separate markdown file for each manuscript.
  The markdown file will be located in the `abstracts` folder, inside a folder with the same date as the mailing list.
- `--modify` or `-m`: Do not modify the authors file (sort and remove blank lines).
- `--image` or `-i`: Remove the images to the markdown file.
  The image is the first figure in the abstract.
- `--threads` or `-t`: Number of threads used to detect the figures, and of processes that save them as images, from 1
  (default) to the number of CPUs of the system.
  Each thread processes a PDF at a time, so more threads are faster but use more memory.
- `--date0`: Specify the date of the first mailing list to be sorted.
  The date should be in the format `YYYYMMDD`.
  If the date is not specified, the program will search for the latest file in the `abstracts` folder.
- `--datef`: Specify the date of the last mailing list to be sorted.
  The date should be in the format `YYYYMMDD`.
  If the date is not specified, this will be the current date.

## Graphical interface

Besides the command line, arXiv-sorter can be used from a graphical interface (built with
[PySide6](https://doc.qt.io/qtforpython-6/)) that works on Windows, macOS and Linux.
Download the archive for your system from the [release page](https://github.com/Davtax/arXiv-sorter/releases):

- **Windows**: `arXiv-sorter-GUI-Windows.zip`. Extract `arXiv-sorter-GUI-Windows.exe` to the folder where you want to keep
  your files, and run it.
- **macOS**: for Apple silicon. The easiest way is to open the Terminal in the folder where you want to keep your files
  and run

  ```bash
  curl -fsSL https://raw.githubusercontent.com/Davtax/arXiv-sorter/main/scripts/install_macos.sh | bash
  ```

  which downloads the latest `arXiv-sorter-GUI-macOS.app` there (run it again to update it). The app is not notarized
  by Apple, so macOS blocks it when it is downloaded with a browser; downloaded this way, it opens directly.
  Alternatively, download `arXiv-sorter-GUI-macOS.zip`, extract `arXiv-sorter-GUI-macOS.app` and move it to that
  folder. Then either run `xattr -dr com.apple.quarantine arXiv-sorter-GUI-macOS.app` in that folder, or open the app,
  go to System Settings -> Privacy & Security and click Open Anyway.
- **Linux**: `arXiv-sorter-GUI-Ubuntu.tar.gz`, built on Ubuntu 22.04 (it runs on distributions with glibc 2.35 or
  newer). Extract it with `tar -xzf arXiv-sorter-GUI-Ubuntu.tar.gz` to the folder where you want to keep your files,
  and run `./arXiv-sorter-GUI-Ubuntu`.
  Qt requires the XCB cursor library, e.g. `sudo apt install libxcb-cursor0` on Debian and Ubuntu.

On Windows and Linux the program is a single file, which unpacks itself in a temporary folder each time it starts (this
takes a few seconds), and deletes it when the window is closed.
If the temporary folder of the system does not allow running programs (e.g. `/tmp` mounted with `noexec`), choose
another one with the `TMPDIR` environment variable.

By default, the keyword files and the abstracts are next to the program (next to `arXiv-sorter-GUI-macOS.app` on macOS), and
other folders can be chosen in the window.
From the source code (see [Development](#development)), start it with

```bash
arxiv-sorter-gui
```

In the window you can:

- Select the keywords and abstracts directories, and see how many keywords, authors and categories you are searching
  (files with mistakes are flagged with ❌).
- Edit `keywords.txt`, `authors.txt` and `categories.txt`, with the mistakes highlighted while typing, and preview which
  submissions of the latest mailing list they would find.
- Tick the optional arguments described above, including the detailed (verbose) messages.
- Search automatically from the last saved abstracts until today, or choose a custom date range (`--date0` and
  `--datef`).
- Follow the progress and the messages of the program (warnings and errors are highlighted), and stop it at any time.
- When it finishes, open the new Markdown files directly from the summary, or with *Open the latest file*.
- Copy or save the messages, or open the log file of the last run, e.g. to report a problem (*Help → Report a
  problem*).
- Choose a light or dark theme, or follow the one of the system (*View → Theme*, or the button in the bottom right
  corner).
- Update to new versions: when the window opens, it checks the [latest release](https://github.com/Davtax/arXiv-sorter/releases/latest)
  in the background. If there is a newer one, a message offers to **Upgrade** (it downloads the new version, replaces
  the program in its folder, and opens it again) or to **Skip** it (it is not offered again when the window opens, but
  *Help → Check for updates…* still installs it). The previous version is deleted the next time the program starts.

### Daily run in the background

arXiv-sorter can run every day at a given time without opening the window: *File → Run every day…*, or the ⏰ button
in the bottom right corner, which shows the current time of the daily run.
The same dialog changes the time, or removes the daily run (untick *Run arXiv-sorter every day at*).

The daily run uses the folders and options of the window (saved when the time is chosen, when the program runs and when
the window closes), always from the last saved abstracts, and shows a notification when it finishes: click it to open
the latest file, or the log if something went wrong.
If the computer is off or asleep at that time, it runs as soon as possible (on macOS, only after sleeping, not after
being off).

The schedule is kept by the operating system, which runs the program with `--scheduled`:

- **Windows**: the task *arXiv-sorter daily run* of the Task Scheduler, while you are logged in.
- **macOS**: the launch agent `~/Library/LaunchAgents/io.github.davtax.arxiv-sorter.daily.plist`. It runs without
  an icon in the Dock and without taking the focus. macOS asks once to allow its notifications, and may show a
  *Background Items Added* message. If the app is moved, opening it once updates the daily run. It cannot be
  scheduled while macOS runs the app from a temporary copy (downloaded with a browser and not moved with the Finder).
- **Linux**: the systemd user timer `arxiv-sorter-daily.timer` (`systemctl --user list-timers`). The notification is
  shown with `notify-send`, when available.

Only one run of arXiv-sorter works at a time: if it is already running (from the window, a terminal or the daily run),
a new run is refused, and a daily run is skipped with a notification.

If you move the program to another folder, choose the time again, so the schedule starts it from its new location.

The configuration is saved when the program runs and when the window closes, and restored at the next start.
It is stored in `settings.json` (next to PDFFigures2), inside `%LOCALAPPDATA%\arXiv-sorter` on Windows,
`~/Library/Preferences/arXiv-sorter` on macOS, and `~/.config/arXiv-sorter` on Linux.

## Development

The program requires Python 3.14. Install it in editable mode, together with the development tools, with

```bash
pip install -e ".[dev]"
```

(`pip install -r requirements-dev.txt` does the same).
This installs the `arxiv-sorter` command (the same optional arguments apply) and the `arxiv-sorter-gui` command, which
can also be run as `python -m arxiv_sorter` and `python -m arxiv_sorter.gui`.
When run from Python, the relative paths are relative to the current directory, while the binaries use the directory
where they are located.

The source code follows the [src layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/):

```bash
src/arxiv_sorter/
├── __init__.py      # Version of the program
├── cli.py           # Command line arguments
├── pipeline.py      # Main workflow: request, sort and write the entries of each day
├── arxiv_api.py     # Requests to the arXiv API
├── dates.py         # Mailing dates
├── sorting.py       # Search of keywords, authors and categories
├── formatting.py    # Markdown output
├── figures.py       # Download of the PDFs and extraction of the first figure
├── user_files.py    # Keywords, authors and categories files
├── search_terms.py  # Check of the search files (mistakes with their file and line)
├── preview.py       # Matches of the search terms in the latest mailing list (search files editor)
├── updater.py       # New versions in GitHub: check, download and replace the binary
├── console.py       # Messages, questions and progress bars
├── log_file.py      # Log file of each run
├── network.py       # Concurrent HTTP requests (pool of threads)
├── system.py        # Platform dependent details
├── protocol.py      # Communication between the GUI and the program
└── gui/             # Graphical interface (PySide6)
```

The files `run.py` and `gui.py` are the launchers used to build the binaries with PyInstaller.

The tests use [pytest](https://docs.pytest.org/) (with [pytest-qt](https://pytest-qt.readthedocs.io/) for the
graphical interface), the code is linted with [ruff](https://docs.astral.sh/ruff/) and type checked with
[mypy](https://mypy.readthedocs.io/), all configured in `pyproject.toml`:

```bash
pytest               # unit tests (no internet connection required)
pytest -m network    # tests that make real requests to the arXiv API
ruff check .         # lint (use --fix to fix the automatically fixable issues)
mypy                 # type check
```

### Continuous integration

Three GitHub Actions workflows check the changes and publish the releases:

- **Tests** (`.github/workflows/tests.yml`), in every pull request (as the first job of the build workflow) and push
  to `main`: ruff, mypy and [actionlint](https://github.com/rhysd/actionlint) (for the workflows), and the tests with
  coverage on Windows, macOS and Linux. In the pull requests into `main`, it also checks that `__version__` is larger
  than the one in `main`. Every Monday, and when run by hand from the Actions tab, the tests against the real arXiv
  and GitHub servers also run.
- **Build** (`.github/workflows/build.yml`), in every pull request, after the tests pass: builds the command line and
  GUI binaries for the three systems, runs them (detecting a single figure), and checks that they write the same
  abstracts. The binaries are always built in the pull requests into `main`, and in the others only if they change the
  program or its packaging. It can also be run by hand from the Actions tab, to build any branch. The binaries can be
  downloaded from the summary of the run for 14 days.
- **Release** (`.github/workflows/release.yml`), when a pull request into `main` is merged: creates a draft release
  with the archives built in the pull request (see below).

[Dependabot](.github/dependabot.yml) opens pull requests into `dev` every month to update the actions and the
dependencies. The folder `scripts/` contains the helper scripts of the workflows.

### Releases

Every pull request into `main` is a release, so the changes are made in `dev` (or merged into it):

1. Update `__version__` in `src/arxiv_sorter/__init__.py` in `dev`.
2. Open a pull request from `dev` into `main`. The tests run, and then the six archives are built, tested and attested.
3. Merge it. The release workflow creates a draft release with the archives of the pull request (they are not built
   again), their checksums (`SHA256SUMS.txt`) and the notes of the changes. Review it on GitHub and publish it, which
   creates the tag `v<version>` on the merged commit. The workflow stops if `main` changed after the pull request was
   built (update the pull request with `main` before merging), or if the tag already exists.

Each archive has a signed [build provenance](https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations)
that shows it was built by the workflow in the pull request of the release. Check it with

```bash
gh attestation verify arXiv-sorter-GUI-Windows.zip --repo Davtax/arXiv-sorter
```
