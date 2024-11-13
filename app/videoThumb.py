import os
import subprocess
import moviepy.editor as mp
from datetime import datetime
from fpdf import FPDF, TextStyle
import json
from typing import List, Dict, Tuple


class VideoAnalyzer:
    """
    Generate a PDF report with video metadata and thumbnails
    from base directory for all videos in subdirectories
    """

    def __init__(self, directory: str):
        self.directory = directory
        self.video_data: List[Dict[str, str | Tuple[int, int] | List[str]]] = []

    def analyze_videos(self) -> None:
        for root, _, files in os.walk(self.directory):
            for file in files:
                if file.lower().endswith(
                    (".mp4", ".avi", ".mov", ".mkv", ".wmv", "m4v")
                ):
                    video_path = os.path.join(root, file)
                    self.extract_metadata(video_path.replace("\\", "/"))

    def extract_metadata(self, video_path: str) -> None:
        video = mp.VideoFileClip(video_path)
        print(f"{video_path=}")

        size_in_byte = os.path.getsize(video_path)
        if size_in_byte < 1024:
            size = str(size_in_byte) + " bytes"
        elif size_in_byte < 1024 * 1024:
            size = str(round(size_in_byte / 1024, 3)) + " KB"
        elif size_in_byte < 1024 * 1024 * 1024:
            size = str(round(size_in_byte / (1024 * 1024), 3)) + " MB"
        else:
            size = str(round(size_in_byte / (1024 * 1024 * 1024), 3)) + " GB"

        duration = video.duration
        resolution: Tuple[int, int] = video.size
        fps = round(video.fps, 3)

        # Get codec and bitrate using ffprobe
        ffprobe_output = self.get_ffprobe_metadata(video_path)
        video_codec = ffprobe_output.get("video_codec", "Unknown")
        audio_codec = ffprobe_output.get("audio_codec", "No audio")
        bitrate = ffprobe_output.get("bit_rate", "Unknown")

        thumbnails = self.generate_thumbnails(video, video_path)

        self.video_data.append(
            {
                "path": video_path,
                "size": size,
                "duration": duration,
                "resolution": resolution if resolution else (0, 0),  # This is a tuple
                "bitrate": bitrate,
                "fps": fps,
                "video_codec": video_codec,
                "audio_codec": audio_codec,
                "thumbnails": thumbnails,
            }
        )

    def get_ffprobe_metadata(self, video_path: str) -> Dict[str, str]:
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
        bit_rate_string = (
            streams[0].get("bit_rate", "Unknown") if len(streams) > 0 else "Unknown"
        )
        bit_rate_string = (
            streams[0]["tags"].get("BPS", "Unknown")
            if bit_rate_string == "Unknown"
            else bit_rate_string
        )
        bit_rate = (
            str(int(bit_rate_string) // 1000) + "kbps"
            if bit_rate_string != "Unknown"
            else "Unknown"
        )

        return {
            "video_codec": video_codec,
            "audio_codec": audio_codec,
            "bit_rate": bit_rate,
        }

    def generate_thumbnails(
        self, video: mp.VideoFileClip, video_path: str
    ) -> List[str]:
        thumbnails = []
        total_duration = video.duration
        print(f"Total duration: {total_duration}")

        for i, time in enumerate(self._generate_sequence(total_duration)):
            filename = os.path.basename(video_path)
            directory = os.path.dirname(video_path)
            os.makedirs(f"{directory}/thumbnails", exist_ok=True)
            thumbnail_path = f"{directory}/thumbnails/{filename}_thumb_{i + 1}.jpg"
            video.save_frame(thumbnail_path, t=time)  # Save frame at calculated time
            thumbnails.append(thumbnail_path)

        return thumbnails

    def generate_pdf(self, output_path: str) -> None:
        """Generate a PDF report containing video analysis data and thumbnails.

        Args:
            output_path (str): Path where the PDF file will be saved
        """
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_image_filter("DCTDecode")
        pdf.oversized_images = "DOWNSCALE"
        pdf.oversized_images_ratio = THUMBNAILS_DENSITY
        pdf.add_font("msyh", "", "c:/windows/fonts/msyh.ttc", uni=True)
        pdf.add_font("msyh", "B", "c:/windows/fonts/msyhbd.ttc", uni=True)

        self._add_report_header(pdf)

        for video in self.video_data:
            pdf.set_font(family="msyh", style="", size=12)
            title = str(video["path"]).split("/")[-1]
            pdf.start_section(title, level=0)
            self._add_video_metadata(pdf, video)
            thumbnails = (
                video["thumbnails"]
                if isinstance(video["thumbnails"], list)
                else ["something wrong"]
            )
            self._add_thumbnail_table(pdf, thumbnails)
            pdf.ln(2)  # Add space between videos

        pdf.output(output_path)

    def _generate_sequence(self, initial_number: float) -> List[int]:
        """
        Generate a sequence of numbers based on the initial number.

        Args:
            initial_number (float): The initial number to generate the sequence from
        """

        # 根据初始数字计算生成数字的个数
        num_count = int(
            min(MAX_THUMBNAILS_COUNT, max(1, initial_number // INCREMENT_BY_SECONDS))
        )

        # 计算步长，使得数列均匀分布在初始数字区间中
        step = initial_number / (num_count + 1)

        # 生成数列
        sequence = [int((i + 1) * step) for i in range(num_count)]
        print("capture at: ", sequence)

        return sequence

    def _add_report_header(self, pdf: FPDF) -> None:
        """Add the report header to the PDF.

        Args:
            pdf (FPDF): The PDF document object
        """
        pdf.add_page()
        # pdf.insert_toc_placeholder(lambda toc: toc)
        pdf.set_font("msyh", size=16, style="B")
        pdf.cell(0, 10, "VideoThumb Report", ln=True, align="C")
        pdf.set_section_title_styles(
            TextStyle(
                font_family="msyh",
                font_style="B",
                font_size_pt=16,
                color=128,
                underline=True,
                t_margin=10,
                l_margin=10,
                b_margin=0,
            )
        )
        pdf.ln()

    def _add_video_metadata(self, pdf: FPDF, video: dict) -> None:
        """Add video metadata section to the PDF.

        Args:
            pdf (FPDF): The PDF document object
            video (dict): Dictionary containing video metadata
        """
        pdf.ln()
        pdf.set_font("msyh", size=10)
        with pdf.table(width=int(pdf.epw), col_widths=(1, 2, 1, 2)) as table:
            row = table.row()
            row.cell("Video Path")
            row.cell(video["path"], colspan=3)

            row = table.row()
            row.cell("Duration")
            row.cell(f"{int(video["duration"] // 60)} minutes")
            row.cell("Resolution")
            row.cell(f"{video["resolution"][0]}x{video["resolution"][1]}")

            row = table.row()
            row.cell("Bitrate")
            row.cell(video["bitrate"])
            row.cell("FPS")
            row.cell(str(video["fps"]))

            row = table.row()
            row.cell("Video Codec")
            row.cell(video["video_codec"])
            row.cell("Audio Codec")
            row.cell(video["audio_codec"])

            row = table.row()
            row.cell("Size")
            row.cell(video["size"])

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
            try:
                # Normalize the path for FPDF
                normalized_thumbnail = thumbnail.replace("\\", "/")  # xdream

                # Check if the image exists before adding
                row.append(normalized_thumbnail)
            except Exception as e:
                print(f"Error loading image {thumbnail}: {e}")  # Log any errors

            if (i + 1) % 4 == 0:
                table_data.append(row)
                row = []

        # Add remaining thumbnails if any
        if row:
            table_data.append(row)

        # Generate the table
        with pdf.table() as table:
            for i, data_row in enumerate(table_data):
                row = table.row()
                for j, data_cell in enumerate(data_row):
                    row.cell(img=data_cell)

        # Reset the table data structure
        table_data.clear()


if __name__ == "__main__":
    BASE_DIRECTORY = "V:/剧集精选/RIPLEY (2024)"
    # BASE_DIRECTORY = "d:/CodeBase/videoThumb/videos"
    # 最多的数字个数为16
    MAX_THUMBNAILS_COUNT = 16
    # 每增加10分钟，数列中多一个数字
    INCREMENT_BY_SECONDS = 10 * 60
    # 缩略图清晰度，默认为4，建议不要超过8，因为会完全没有必要的占用空间。
    THUMBNAILS_DENSITY = 4

    # 生成当前日期字符串
    current_date = datetime.now().strftime("%Y-%m-%d")

    output_pdf = f"{BASE_DIRECTORY}/{BASE_DIRECTORY.split('/')[-1]}.report.{current_date}.pdf"  # Predefined output PDF path

    analyzer = VideoAnalyzer(BASE_DIRECTORY)
    analyzer.analyze_videos()
    analyzer.generate_pdf(output_pdf)
    print("PDF generated successfully.")
