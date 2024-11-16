# purpose

This simple local video tool is designed to help you efficiently organize video files. It serves as a convenient reference, especially when you're dealing with a large number of video files that are difficult to describe with filenames or other text-based descriptors. To ensure the final PDF document is visually appealing and easy to read, the tool generates up to 16 thumbnails by default. Each video file in generated PDF is labeled for easy navigation and searching.

这个简单的视频整理工具旨在帮助您高效地组织本地视频文件。特别是在面对大量难以用文件名或其他文本描述的情况下，它可以作为一个便捷的参考工具。为了确保生成的 PDF 文档美观易读，默认情况下工具会生成多达 16 个缩略图，并在 PDF 中添加文件名标签，以便于导航和搜索。

# requirements

ffmpeg need to be installed, and ffprobe.exe should be in PATH, and python of course. choco is recommanded way.
```sh
choco install python ffmpeg

# and then in the project folder.
pip install -r requirements.txt
```

# third party modules

moviepy fpdf2 tqdm pydantic

# args

| Option | Description  |
| ------ | ------------ |
| `-h`, `--help` | Show this help message and exit.  |
| `-b BASE`, `--base BASE` | Base path of the video folder. If not present, the base path would be './videos'.   |
| `-e EXTENSION`, `--extension EXTENSION` | Add more filename extensions to parse as a video. Default extensions are ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.m4v']. You could add a list like '-e webv,webp,...'. |
| `-k`, `--keep` | Keep the thumbnails after generating the PDF report. If not present, the thumbnails would be deleted. |
| `-m MAX`, `--max MAX` | Maximum number of thumbnails to generate per video. If not present, the default value is 16.   |

# tips

If a video file is not smooth or is corrupted, it might cause the program to freeze. You can try running the program again with target directory specifically to those files, which might resolve the issue.

# problems

~~for some video file, process may hang up while building thumbnails, to solve that, for now, you could try to locate that file, from logs, and then rename that video by adding a prefix 'tui-'. tried, failed. try opencv next time~~

log: changed back to moviepy, it runs slower than with opencv, but with threading timeout function, it could avoid most of errors.

# thanks

micorsoft copilot and openai

# todo

~~try pdf.unbreakable() for metadata table. not work as expected.~~

~~use analyze_log for pdf gen.~~

