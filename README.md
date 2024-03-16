![GitHub Release](https://img.shields.io/github/v/release/Davtax/arXiv-sorter?display_name=release)


# arXiv-sorter

Sort the daily arXiv mail list by user keywords, and output the manuscripts in a nice markdown.
The program is written in Python and compiled into a binary file using [PyInstaller](https://www.pyinstaller.org/).

The output file is a markdown file, which is intended to be used with the [Obsidian](https://obsidian.md/) note-taking
app.
The program creates a file for each mailing list, with the named `YYYY-MM-DD.md`, where `YYYY-MM-DD` is the date of the
mail.
The markdown file is located inside the abstracts folder, which is created in the same directory as the binary file.

In the markdown file, each entry for the manuscript contains the title, authors list, abstract, the first figure of the
manuscript, a link to the manuscript, and the date of submission.
The user can specify keywords to search for in the title, abstract, and authors list of the manuscript.
If the manuscript contains the keywords, this manuscript will be sorted at the top of the markdown file.
Furthermore, the matching keywords will be highlighted in the title and abstract of the manuscript.
The color code for the highlighting is the following:

- $\color{red}\textsf{Red}$ for the title
- $\color{green}\textsf{Green}$ for the authors
- $\color{red}\textsf{Red}$ for the abstract
- $\color{yellow}\textsf{Yellow}$ for a combination of keywords
- $\color{green}\textsf{Green}$ for overlapping keywords

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
However, not all the manuscripts are automatically converted to HTML, and the program will not be able to extract the
image.

> [!IMPORTANT]  
> Since the program relies on the name of the markdown file to search for the latest file, do not rename the markdown
> files.

## Usage

1. (Only the first time) Install Obsidian, adn configure a new Obsidian vault (or use the default one).
2. Download the corresponding zip file from the [release page](https://github.com/Davtax/arXiv-sorter/releases).
3. Extract the zip file.
4. Place the binary file in the directory where you want to save the output file.
5. (Only the first time) Create the keyword files in the same directory as the binary file. The keyword files should be
   named `authors.txt`, `categories.txt`, and `keywords.txt`. The content of the file should be the keywords you want
   to search for, one keyword per line. If the program is run without the keyword files, the program will create the
   empty files.
6. Run the binary files. The program will search for the latest file in the `abstracts` folder, and output the markdown
   files between that date and the current date.

The final directory tree should looks (if using defaut paths) somethig like:
```bash
├── arXiv-sorter
│   ├── .obsidian
│   │   ├── snippets
│   │   │   └── arXiv-sorter.css  
│   ├── abstracts
│   │   ├── YYYYMMDD(1).md
│   │   ├── YYYYMMDD(2).md
│   │   └── YYYYMMDD(3).md
│   ├── arXiv-sorter-*
│   ├── authors.txt
│   ├── categories.txt
└── └── keywords.txt

```

> [!NOTE]  
> Some antivirus programs may block the execution of the binary file.
> In this case, you can add the binary file to the exception list of the antivirus program.
> If you are using Windows, you can run the binary file as an administrator.

> [!NOTE]  
> On Mac, when downloading a new version, and unidentified developer warning pop-up.
> To solve that, Right click -> Open -> Open.
> Once solved, the message will dissapear.

> [!WARNING]  
> Sometimes the arXiv API does not respond, and the program will keep running indefinitely. In this case, you can close
> the terminal, and the program will stop. Try to run the program in a few minutes.

## Keywords

In each line of the keyword files, you can specify the keywords you want to search for.
The program will search for the keywords in the title, abstract, and authors of the manuscript.
The program is case-insensitive, and the keywords can be written in any case.
Inside the `keywords.txt`, you can combine multiple keywords in the same line using the `+` character.
The program will search for the manuscripts that contain all the keywords in the same line.
You can comment out a line by starting the line with the `#` character.

After the program is run, the authors inside the `authors.txt` file will be sorted alphabetically.

A list of all possible arXiv categories can be found [here](https://arxiv.org/category_taxonomy).
If you are interested in all the groups of a category, just write the category letters in the `categories.txt` file.

## CSS snippets

The program can make use of the CSS snippets to format the markdown file inside Obsidian.
The CSS snippets are located in the [snippets](https://github.com/Davtax/arXiv-sorter/tree/main/snippets) folder.
To install the CSS snippets, copy the content of the CSS snippets to the `.obsidian/snippets` folder in the home
directory.
Then, open the Obsidian app, and enable the CSS snippets in the Settings/Appearance/CSS snippets option.

This option is purely stylistic, and it is not necessary to run the program.

## Optional arguments

When running the program from the terminal, you can use the following optional arguments:

- `--help` or `-h`: Show the help message and exit.
- `--verbose` or `-v`: Print the output to the terminal.
- `--directory` or `-d`: Specify the directory where the keyword files are located. The default value is the current
  directory (`./`).
- `--abstracts` or `-a`: Specify the directory where the abstracts are located. The default value is the `abstracts`
  folder in the current directory (`/abstracts`).
- `--time` or `-t`: Specify the terminal closing time in seconds. The default value is 3 seconds.
- `--final` or `-f`: Remove the final time stamp from the markdown file.
- `--update` or `-u`: Check if there is a new version of the program available in GitHub, and update the program if
  true. (TO BE IMPLEMENTED)
- `-image` or `-i`: Remove the images to the markdown file. The image is the first figure in the abstract.
- `--date0`: Specify the date of the first mailing list to be sorted. The date should be in the format `YYYYMMDD`. If the
  date is not specified, the program will search for the latest file in the `abstracts` folder.
- `--date0`: Specify the date of the last mailing list to be sorted. The date should be in the format `YYYYMMDD`. If the
  date is not specified, this will be the current date.
