# arXiv-sorter
Sort the daily arXiv mail list by user keywords, and output the manuscripts in a nice markdown.
The program is written in Python and compiled to a binary file using [PyInstaller](https://www.pyinstaller.org/).

The output file is a markdown file, which is intended to be used with the [Obsidian](https://obsidian.md/) note-taking app.
The program create a  file for each mailing list, with the named `YYYY-MM-DD.md`, where `YYYY-MM-DD` is the date of the mail.
The markdown file is located inside the abstracts folder, which is created in the same directory as the binary file. 

## Usage
1. Download the binary file from the [release page](https://github.com/Davtax/arXiv-sorter/releases).
2. Place the binary file in the directory where you want to save the output file.
3. (Only mac) Open the terminal and run the following command to give the binary file the permission to run
```bash chmod 755 arXiv-sorter-macOS```.
4. (Only the first time) Create the keyword files in the same directory as the binary file. The keyword files should be named as `authors.txt`, `categories.txt` and `keywords.txt`. The content of the file should be the keywords you want to search for, one keyword per line. If the program is run without the keyword files, the program will create the empty files.
5. Run the binary files. The program will search for the latest file in the `abstracts` folder, and output the markdown files between that date and the current date.

> [!WARNING]  
> Sometimes the arXiv API does not respond, and the program will keep running indefinitely. In this case, you can close the terminal, and the program will stop. Try to run the program in a few minutes.


## Keywords
In each line of the keyword files, you can specify the keywords you want to search for.
The program will search for the keywords in the title, abstract, and authors of the manuscript.
The program is case-insensitive, and the keywords can be written in any case.
Inside the `keywords.txt`, you can combine multiple keywords in the same line using the `+` character.
The program will search for the manuscripts that contain all the keywords in the same line.

After the program is run, the authors inside the `authors.txt` file will be sorted alphabetically. 

A list for all possible arXiv categories can be found [here](https://arxiv.org/category_taxonomy).
If you are interested in all the groups of a category, just write the category letters in the `categories.txt` file.

## CSS snippets
The program can make use of the CSS snippets to format the markdown file inside Obsidian.
The CSS snippets are located in (snippets)[] folder.
To install the CSS snippets, copy the content of the CSS snippets to the `.obsidian/snippets` folder in the home directory.
Then, open the Obsidian app, and enable the CSS snippets in the Settings/Appearance/CSS snippets option.

This option is pure stylistic, and it is not necessary to run the program.

## Optional arguments
When running the program from the terminal, you can use the following optional arguments:
- `--help` or `-h`: Show the help message and exit.
- `--verbose` or `-v`: Print the output to the terminal.
- `--directory` or `-d`: Specify the directory where the keyword files are located. The default value is the current directory.
- `time` or `-t`: Specify the terminal closing time in seconds. The default value is 3 seconds.
- `--abstracts` or `-a`: Specify the directory where the abstracts are located. The default value is the `abstracts` folder in the current directory.
- `--update` or `-u`: Check if there is a new version of the program available in GitHub, and update the program if true. (TO BE IMPLEMENTED)
- `-image` or `-i`: Remove the images to the markdown file. The image is the first figure in the abstract.