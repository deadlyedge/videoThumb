# purpose

This is a simple local video tool designed to help you organize videos efficiently. It serves as a handy reference, especially when dealing with a large number of video files that are difficult to describe using filenames or other textual or language-based descriptors. To ensure the final PDF document is visually appealing and easy to read, the tool generates up to 16 thumbnails by default. The resulting PDF is labeled for easy navigation and searching.

# requirements

ffmpeg need to be installed, and ffprobe.exe should be in PATH, choco is recommanded way.

# problems

for some video file, process may hang up while building thumbnails, to solve that, for now, you could try to locate that file, from logs, and then rename that video by adding a prefix 'tui-'. tried, failed. try opencv next time

# thanks

micorsoft copilot

# todo

try opencv next time