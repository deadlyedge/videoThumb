import os
import threading
import subprocess
import argparse
import json

from concurrent.futures import ThreadPoolExecutor, as_completed
from moviepy import editor as mp
from datetime import datetime
from typing import List, Dict, Tuple
from fpdf import FPDF, TextStyle
from tqdm import tqdm
from pydantic import BaseModel


DEFAULT_FORMATS = [".mp4", ".avi", ".mov", ".mkv", ".wmv", ".m4v", ".mpeg", "mpg"]
DEFAULT_THUMBNAIL_PATH = "videoThumbs"
DEFAULT_FONT_FAMILY = "Noto"
DEFAULT_FONT_PATH = "./fonts/NotoSerifSC-Regular.ttf"
DEFAULT_FONT_BOLD_PATH = "./fonts/NotoSerifSC-Bold.ttf"

# this is for optimizing of computer resource, don't change it if you not sure.
DEFAULT_HANG_TIME = 3
DEFAULT_MAX_THREADING_WORKERS = 4  # tested in a 1Gbps network drive


class VideoData(BaseModel):
    path: str
    size: str
    duration: float = 0.0
    resolution: Tuple[int, int] = (0, 0)
    bitrate: str = "Unknown"
    fps: float = 0.0
    video_codec: str = "Unknown"
    audio_codec: str = "Unknown"
    thumbnails: List[str] = []
    failed_reason: str = ""


class VideoReaderWithTimeout:
    def __init__(
        self,
        video_path: str,
        index: int,
        time: int,
        pbar: tqdm,
        video: mp.VideoFileClip,
    ):
        self.video_path = video_path
        self.index = index
        self.time = time
        self.pbar = pbar
        self.video = video
        self.thumbnail_path = None

    def save_frame(self) -> None:
        filename = os.path.basename(self.video_path)
        directory = os.path.dirname(self.video_path)
        os.makedirs(f"{directory}/{DEFAULT_THUMBNAIL_PATH}", exist_ok=True)
        thumbnail_path = (
            f"{directory}/{DEFAULT_THUMBNAIL_PATH}/{filename}_thumb_{self.index}.jpg"
        )

        try:
            self.video.save_frame(thumbnail_path, t=self.time)
        except Exception as error:
            self.pbar.write(f"Error processing {self.video_path}: {error}")
            thumbnail_path = ""

        self.thumbnail_path = thumbnail_path


def read_with_timeout(
    video_path: str,
    index: int,
    time: int,
    pbar: tqdm,
    video: mp.VideoFileClip,
    timeout=DEFAULT_HANG_TIME,
):
    reader = VideoReaderWithTimeout(video_path, index, time, pbar, video)
    thread = threading.Thread(target=reader.save_frame)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        # Timeout occurred
        red_color_start = "\033[91m"  # ANSI escape code for red
        color_end = "\033[0m"  # ANSI escape code to reset
        pbar.write(
            f"{red_color_start}Timeout occurred while processing{color_end} {video_path}"
        )
        return ""
    else:
        # Successfully read frame before timeout
        return reader.thumbnail_path


class VideoAnalyzer:
    """
    Generate a PDF report with video metadata and thumbnails
    from base directory for all videos in subdirectories
    """

    def __init__(self, directory: str):
        self.directory = directory
        self.video_data: List[VideoData] = []
        self.lock = threading.Lock()

    def analyze_videos(self) -> None:
        """
        Start point for analyzing videos in the specified directory.
        Uses ThreadPoolExecutor to parallelize metadata extraction.
        """
        video_files = [
            os.path.join(root, file).replace("\\", "/")
            for root, _, files in os.walk(self.directory)
            for file in files
            if file.lower().endswith(tuple(SUPPORTED_FORMATS))
        ]

        if len(video_files):
            self.pbar = tqdm(total=len(video_files), desc="Analyzing")
            with ThreadPoolExecutor(
                max_workers=DEFAULT_MAX_THREADING_WORKERS
            ) as executor:
                futures = {
                    executor.submit(self._extract_metadata, video_path): video_path
                    for video_path in video_files
                }

                for future in as_completed(futures):
                    video_path = futures[future]
                    try:
                        future.result()  # Can be used to raise exceptions if any occurred
                    except Exception as error:
                        self.pbar.write(f"Error processing {video_path}: {error}")
                    finally:
                        self.pbar.update(1)
            self.pbar.close()
        else:
            raise Exception('NO video found, check BASE path you provided with "-b".')

    def clean_thumbnails(self) -> None:
        """
        Removes the thumbnail directory for each video path based on
        the entries in the analyze_log.json.
        """
        log_path = os.path.join(self.directory, "analyze_log.json")
        if not os.path.exists(log_path):
            self.pbar.write("No analyze_log.json found. Skipping cleanup.")
            return

        with open(log_path, "r", encoding="utf-8") as f:
            video_logs = json.load(f)

        for video_entry in video_logs:
            video_path = video_entry["path"]
            thumbnail_dir = os.path.join(
                os.path.dirname(video_path), DEFAULT_THUMBNAIL_PATH
            )

            if os.path.exists(thumbnail_dir):
                for root, dirs, files in os.walk(thumbnail_dir, topdown=False):
                    for name in files:
                        os.remove(os.path.join(root, name))
                    for name in dirs:
                        os.rmdir(os.path.join(root, name))
                os.rmdir(thumbnail_dir)
                self.pbar.write(f"Removed thumbnails directory: {thumbnail_dir}")
            else:
                self.pbar.write(f"Thumbnails directory passed: {video_path}")

    def _extract_metadata(self, video_path: str) -> None:
        """
        use moviepy to extract metadata from the video file
        """

        def format_size(size_in_bytes):
            if size_in_bytes < 1024:
                return f"{size_in_bytes} bytes"
            elif size_in_bytes < 1024 * 1024:
                return f"{round(size_in_bytes / 1024, 3)} KB"
            elif size_in_bytes < 1024 * 1024 * 1024:
                return f"{round(size_in_bytes / (1024 * 1024), 3)} MB"
            else:
                return f"{round(size_in_bytes / (1024 * 1024 * 1024), 3)} GB"

        try:
            video = mp.VideoFileClip(video_path)
            orange_color_start = (
                "\033[33m"  # ANSI escape code for orange (bright yellow)
            )
            color_end = "\033[0m"  # ANSI escape code to reset color
            self.pbar.write(f"{orange_color_start}{video_path=}{color_end}")
            ffprobe_output = self._get_ffprobe_metadata(video_path)

            data = VideoData(
                path=video_path,
                size=format_size(os.path.getsize(video_path)),
                duration=video.duration,
                resolution=video.size,
                bitrate=ffprobe_output["bit_rate"],
                fps=round(video.fps, 3),
                video_codec=ffprobe_output["video_codec"],
                audio_codec=ffprobe_output["audio_codec"],
                thumbnails=self._generate_thumbnails(video, video_path),
            )

        except Exception as error:
            data = VideoData(
                path=video_path,
                size=format_size(os.path.getsize(video_path)),
                failed_reason=str(error),
            )
            red_color_start = "\033[91m"  # ANSI escape code for red
            color_end = "\033[0m"  # ANSI escape code to reset color
            self.pbar.write(
                f"{red_color_start}Error processing {video_path}: {error}{color_end}"
            )
        finally:
            if "video" in locals():
                video.close
            with self.lock:
                self.video_data.append(data)
                self._write_analyze_log()

    def _write_analyze_log(self) -> None:
        log_path = os.path.join(self.directory, "analyze_log.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(
                [data.model_dump() for data in self.video_data],
                f,
                indent=2,
                ensure_ascii=False,
            )

    def _get_ffprobe_metadata(self, video_path: str) -> Dict[str, str]:
        def get_bit_rate(streams: list) -> str:
            if not streams:
                return "Unknown"

            # Attempt to retrieve the bit rate from the first stream
            bit_rate = streams[0].get("bit_rate") or streams[0].get("tags", {}).get(
                "BPS", "Unknown"
            )

            return (
                f"{int(bit_rate) // 1000} kbps" if bit_rate != "Unknown" else "Unknown"
            )

        command = [
            "ffprobe",
            # "-v",
            # "error",
            "-show_streams",
            # "v:1,a:1",
            "-show_entries",
            "stream=codec_name,bit_rate",
            "-of",
            "json",
            video_path,
        ]
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        streams = json.loads(result.stdout).get("streams", [])

        video_codec = streams[0]["codec_name"] if len(streams) > 0 else "Unknown"
        audio_codec = streams[1]["codec_name"] if len(streams) > 1 else "No audio"

        bit_rate = get_bit_rate(streams)

        return {
            "video_codec": video_codec,
            "audio_codec": audio_codec,
            "bit_rate": bit_rate,
        }

    def _generate_thumbnails(
        self, video: mp.VideoFileClip, video_path: str
    ) -> List[str]:
        def generate_sequence(initial_number: float) -> List[int]:
            """
            Generate a sequence of numbers based on the initial number.

            Args:
                initial_number (float): The initial number to generate the sequence from
            """

            # 根据初始数字计算生成数字的个数
            num_count = int(
                min(
                    MAX_THUMBNAILS_COUNT, max(1, initial_number // INCREMENT_BY_SECONDS)
                )
            )

            # 计算步长，使得数列均匀分布在初始数字区间中
            step = initial_number / (num_count + 1)

            # 生成数列
            sequence = [int((i + 1) * step) for i in range(num_count)]
            self.pbar.write(f"capture at: {sequence}")

            return sequence

        thumbnails = []
        total_duration = video.duration
        self.pbar.write(f"Total duration: {round(total_duration / 60)} min.")

        for index, time in enumerate(generate_sequence(total_duration)):
            thumbnail_path = read_with_timeout(
                video_path, index, time, self.pbar, video
            )

            thumbnails.append(thumbnail_path)

        return thumbnails

    def generate_pdf(self, output_path: str) -> None:
        """Generate a PDF report containing video analysis data and thumbnails.
        this function has three sperate sub functions to add header, metadata and thumbnails table to the pdf.

        Args:
            output_path (str): Path where the PDF file will be saved
        """
        self.video_data.sort(key=lambda x: x.path)

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_image_filter("DCTDecode")
        pdf.oversized_images = "DOWNSCALE"
        pdf.oversized_images_ratio = THUMBNAILS_DENSITY
        pdf.add_font(DEFAULT_FONT_FAMILY, "", DEFAULT_FONT_PATH)
        pdf.add_font(DEFAULT_FONT_FAMILY, "B", DEFAULT_FONT_BOLD_PATH)

        self._add_report_header(pdf)

        for video in self.video_data:
            pdf.set_font(style="", size=12)
            title = video.path.split("/")[-1]
            pdf.start_section(title, level=0)

            self._add_video_metadata(pdf, video)
            self._add_thumbnail_table(pdf, video.thumbnails)
            pdf.ln(2)  # Add space between videos

        pdf.output(output_path)

    def _add_report_header(self, pdf: FPDF) -> None:
        """Add the report header to the PDF.

        Args:
            pdf (FPDF): The PDF document object
        """
        pdf.add_page()
        pdf.set_font(family=DEFAULT_FONT_FAMILY, size=16, style="B")
        pdf.cell(0, 10, "VideoThumb Report", ln=True, align="C")
        pdf.set_text_color(100)
        pdf.set_font(size=6)
        pdf.cell(
            0,
            2,
            f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, for '{BASE_DIRECTORY}'",
            ln=True,
            align="C",
        )
        pdf.set_section_title_styles(
            TextStyle(
                font_style="B",
                font_size_pt=14,
                color=(255, 152, 0),
                underline=True,
                t_margin=10,
                l_margin=10,
                b_margin=0,
            )
        )

    def _add_video_metadata(self, pdf: FPDF, video: VideoData) -> None:
        """Add video metadata section to the PDF.

        Args:
            pdf (FPDF): The PDF document object
            video (dict): Dictionary containing video metadata
        """
        pdf.ln()
        pdf.set_font(size=8)
        pdf.set_text_color(50)
        with pdf.table(
            width=int(pdf.epw), col_widths=(1, 2, 1, 2, 1, 2), repeat_headings=0
        ) as table:
            row = table.row()
            row.cell("Video Path")
            row.cell(video.path, colspan=3)
            row.cell("Size")
            row.cell(video.size)

            if video.failed_reason:
                row = table.row()
                pdf.set_font(size=12, style="B")
                pdf.set_text_color(255, 0, 0)
                row.cell("VIDEO FILE IS BROKEN PROBABLY!", colspan=2, align="C")
                row.cell(video.failed_reason, colspan=4)
                return

            row = table.row()
            row.cell("Duration")
            row.cell(f"{video.duration // 60} minutes")
            row.cell("Resolution")
            row.cell(f"{video.resolution[0]}x{video.resolution[1]}")
            row.cell("Bitrate")
            row.cell(video.bitrate)

            row = table.row()
            row.cell("FPS")
            row.cell(str(video.fps))
            row.cell("Video Codec")
            row.cell(video.video_codec)
            row.cell("Audio Codec")
            row.cell(video.audio_codec)

    def _add_thumbnail_table(self, pdf: FPDF, thumbnails: list) -> None:
        """Add a table of thumbnails to the PDF.

        Args:
            pdf (FPDF): The PDF document object
            thumbnails (list): List of thumbnail paths
        """
        # Create table data structure
        table_data = []
        row = []

        for i, thumbnail in enumerate(thumbnails):
            normalized_thumbnail = thumbnail.replace("\\", "/")  # xdream
            row.append(normalized_thumbnail)

            if (i + 1) % 4 == 0:
                table_data.append(row)
                row = []

        # Add remaining thumbnails if any
        if row:
            table_data.append(row)

        # Generate the table
        with pdf.table(repeat_headings=0) as table:
            for i, data_row in enumerate(table_data):
                row = table.row()
                for j, data_cell in enumerate(data_row):
                    if not data_cell:
                        row.cell("failing create this thumbnail.", align="C")
                        continue
                    row.cell(img=data_cell, img_fill_width=True)

        # Reset the table data structure
        table_data.clear()


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="VideoThumb - a thumbnails parser for videos."
    )
    parser.add_argument(
        "-b",
        "--base",
        required=False,
        help="Base path of the video folder, if not present, the base path would be './videos'.",
    )
    parser.add_argument(
        "-e",
        "--extensions",
        required=False,
        help=f"add more filename extensions to parse as a video, default extensions is {DEFAULT_FORMATS}, you could add a list like '-e webv,webp,...'.",
    )
    parser.add_argument(
        "-k",
        "--keep",
        action="store_true",
        help="Keep the thumbnails after generating the PDF report. if not present, the thumbnails would be deleted.",
    )
    parser.add_argument(
        "-m",
        "--max",
        type=int,
        help="Maximum number of thumbnails to generate per video. if not present, the default value is 16.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=False,
        help="Path to the output PDF file, if not present, the output file would be in base direcotry.",
    )
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    args = parse_arguments()

    BASE_DIRECTORY = args.base.replace("\\", "/") if args.base else "./videos"
    # 最多的数字个数为16
    MAX_THUMBNAILS_COUNT = args.max if args.max else 16
    # 每增加8分钟，数列中多一个数字
    INCREMENT_BY_SECONDS = 8 * 60
    # 缩略图清晰度，默认为4，建议不要超过8，因为会完全没有必要的占用空间。
    THUMBNAILS_DENSITY = 4
    # 支持的格式
    SUPPORTED_FORMATS = (
        DEFAULT_FORMATS + args.extensions.split(",")
        if args.extensions
        else DEFAULT_FORMATS
    )

    current_date = datetime.now().strftime("%Y-%m-%d")

    pdf_file_name = f'{BASE_DIRECTORY.split('/')[-1]}.report.{current_date}.pdf'

    output_pdf = (
        os.path.join(args.output, pdf_file_name)
        if args.output and os.path.isdir(os.path.dirname(args.output))
        else f"{BASE_DIRECTORY}/{pdf_file_name}"
    )  # Predefined output PDF path

    analyzer = VideoAnalyzer(BASE_DIRECTORY)

    try:
        analyzer.analyze_videos()
        analyzer.generate_pdf(output_pdf)
        if not args.keep:
            analyzer.clean_thumbnails()

        print("PDF generated successfully.")
    except Exception as error:
        print("Process terminated: ", error)
        print("PDF generation failed.")
