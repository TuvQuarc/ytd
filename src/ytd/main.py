import copy
import logging
import pathlib
import sys
from logging.handlers import RotatingFileHandler
from typing import Annotated, Any, Dict
from urllib.parse import urlparse

import click
import structlog
import typer
import yt_dlp.utils
from yt_dlp import YoutubeDL


class YtDlpStructlogAdapter:
    """
    Adapter class to intercept yt-dlp log messages and route them through structlog.
    yt-dlp requires an object with debug(), warning(), and error() methods.
    """

    def __init__(self, logger: structlog.BoundLogger):
        """
        Initializes the adapter with a structlog logger instance.
        """
        self.logger = logger

    def debug(self, msg: str) -> None:
        """
        Processes yt-dlp debug and info messages.
        yt-dlp sends both standard info messages and debug messages to this method.
        We separate them based on the '[debug]' prefix.
        """
        if not msg.strip():
            return

        if msg.startswith('[debug]'):
            clean_msg = msg.replace('[debug]', '', 1).strip()
            self.logger.debug("yt_dlp_debug", detail=clean_msg)
        else:
            self.logger.info("yt_dlp_info", detail=msg.strip())

    def warning(self, msg: str) -> None:
        """Processes and logs yt-dlp warning messages."""
        if not msg.strip():
            return

        clean_msg = msg.replace('WARNING:', '', 1).strip()
        self.logger.warning("yt_dlp_warning", detail=clean_msg)

    def error(self, msg: str) -> None:
        """Processes and logs yt-dlp error messages."""
        if not msg.strip():
            return

        clean_msg = msg.replace('ERROR:', '', 1).strip()
        self.logger.error("yt_dlp_error", detail=clean_msg)


def setup_logging() -> None:
    """
    Configures structlog and standard logging.
    Sets up a console handler for stdout/stderr and a rotating file handler.
    The log file is saved in the current working directory.
    """
    timestamper = structlog.processors.TimeStamper(fmt='%Y-%m-%d %H:%M:%S')

    base_processors = [
        timestamper,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=base_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(
            colors=sys.stdout.isatty(),
        ),
        foreign_pre_chain=base_processors,
    )

    file_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(ensure_ascii=False),
        foreign_pre_chain=base_processors,
    )

    # Standard output for INFO and DEBUG
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File output (saves in the directory where the command is executed)
    log_file_path = pathlib.Path.cwd() / 'ytd.log'
    file_handler = RotatingFileHandler(
        filename=str(log_file_path),
        maxBytes=10 * 1024 * 1024,
        backupCount=7,
        encoding='utf-8',
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Standard error for ERROR and above
    error_handler = logging.StreamHandler(sys.stderr)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(console_formatter)
    root_logger.addHandler(error_handler)


def get_base_ydl_params(custom_logger: structlog.BoundLogger) -> Dict[str, Any]:
    """
    Returns a fresh dictionary of base yt-dlp configuration options.

    Args:
        custom_logger: The structlog logger instance to be used by yt-dlp.

    Returns:
        Dict[str, Any]: Configuration dictionary.
    """
    return {
        'allow_multiple_audio_streams': True,
        'compat_opts': {'no-certifi'},
        'extract_flat': 'discard_in_playlist',
        'format': (
            'bestvideo+bestaudio[language^=ru]+bestaudio[language^=en]/'
            'bestvideo+bestaudio[language^=ru]/'
            'bestvideo+bestaudio[language^=en]/'
            'bestvideo+bestaudio/best'
        ),
        'ignoreerrors': 'only_download',
        'outtmpl': {
            'default': '',
            'pl_thumbnail': ''
        },
        'postprocessors': [
            {
                'already_have_subtitle': False,
                'key': 'FFmpegEmbedSubtitle'
            },
            {
                'add_chapters': True,
                'add_infojson': 'if_exists',
                'add_metadata': True,
                'key': 'FFmpegMetadata'
            },
            {
                'already_have_thumbnail': False,
                'key': 'EmbedThumbnail'
            },
            {
                'key': 'FFmpegConcat',
                'only_multi_video': True,
                'when': 'playlist'
            }
        ],
        'subtitleslangs': ['ru', 'en'],
        'updatetime': True,
        'warn_when_outdated': True,
        'windowsfilenames': True,
        'writesubtitles': True,
        'writethumbnail': True,
        'merge_output_format': 'mkv/mp4',
        'http_headers': {
            'User-Agent': (
                'Mozilla/5.0 (iPhone17,5; CPU iPhone OS 18_3_2 like Mac OS X) '
                'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 FireKeepers/1.7.0'
            ),
        },
        'continuedl': True,
        'retries': 15,
        'fragment_retries': 15,
        'skip_unavailable_fragments': False,
        'retry_sleep': 5,
        'remote_components': ['ejs:github'],
        'embeddescription': True,
        'noprogress': True,
        # Inject our custom logger adapter
        'logger': YtDlpStructlogAdapter(logger=custom_logger),
    }


def ensure_scheme(url: str) -> str:
    """Ensures the URL has an http/https scheme for proper parsing."""
    if not url.startswith(('http://', 'https://')):
        return f'https://{url}'
    return url


def is_youtube_url(url: str) -> bool:
    """
    Validates if the provided URL points to a known YouTube domain.
    """
    url = ensure_scheme(url)
    host = urlparse(url).hostname or ''

    valid_domains = (
        'youtube.com',
        'youtu.be',
    )

    # Check if the host ends with any of the valid domains
    # (handles www., m., music., etc.)
    return any(host == domain or host.endswith(f'.{domain}') for domain in valid_domains)


def is_single_video(url: str) -> bool:
    """
    Determines whether a YouTube URL points to a single video or a playlist.
    """
    url = ensure_scheme(url)
    parsed = urlparse(url)
    host = parsed.hostname or ''
    path = parsed.path

    # youtu.be links are always single videos
    if host in ('youtu.be', 'www.youtu.be'):
        return True

    # Standard YouTube video paths
    if path.startswith(('/watch', '/shorts/', '/live/')):
        return True

    if path.startswith('/playlist'):
        return False

    raise ValueError(f'Unsupported or invalid YouTube URL structure: "{url}"')


def download_single_video(url: str, params: Dict[str, Any], cookies: str = '') -> None:
    """
    Downloads a single YouTube video.
    Pre-extracts metadata to reliably determine the author/channel name
    and dynamically sets the output filename template.
    """
    local_params = copy.deepcopy(params)

    if cookies:
        local_params['cookiefile'] = cookies

    with YoutubeDL(local_params) as ydl:
        # 1. Extract info safely without downloading the video yet
        info = ydl.extract_info(url, download=False) or {}

        # 2. Safely find the author using dict.get().
        # The 'or' operator will pick the first value that is not None/empty.
        author = (
                info.get('channel') or
                info.get('uploader') or
                info.get('creator') or
                info.get('uploader_id') or
                'Unknown Author'
        )

        # 3. Clean up the author name if it starts with '@'
        if author.startswith('@'):
            author = author[1:]

        # 4. Update the output template dynamically for this specific instance
        ydl.params['outtmpl']['default'] = f'{author} - %(title)s.%(ext)s'

        # 5. Perform the actual download
        ydl.download([url])


def download_playlist(url: str, params: Dict[str, Any], cookies: str = '') -> None:
    """
    Downloads a YouTube playlist, placing videos in a dedicated folder.
    """
    local_params = copy.deepcopy(params)
    local_params['outtmpl']['default'] = '%(channel)s - %(playlist_title)s/%(playlist_index)03d - %(title)s.%(ext)s'

    if cookies:
        local_params['cookiefile'] = cookies

    with YoutubeDL(local_params) as ydl:
        ydl.download([url])


# Initialize Typer App and Logging
app = typer.Typer(add_completion=False)
setup_logging()
logger = structlog.get_logger(__name__)


@app.command()
def main(
        url: Annotated[str, typer.Argument(help='The YouTube URL to download.')],
        cookies: Annotated[str, typer.Option(help='Path to a Netscape-formatted cookies file.')] = '',
) -> None:
    """
    A CLI tool to download videos and playlists from YouTube.
    """
    if not is_youtube_url(url):
        logger.error('invalid_url', url=url)
        raise ValueError(f'Not a valid YouTube URL: "{url}"')

    base_params = get_base_ydl_params(custom_logger=logger)

    if is_single_video(url):
        logger.info('downloading_single_video', url=url)
        download_single_video(url=url, params=base_params, cookies=cookies)
    else:
        logger.info('downloading_playlist', url=url)
        download_playlist(url=url, params=base_params, cookies=cookies)


if __name__ == '__main__':
    logger.info('application_started')
    try:
        app(standalone_mode=False)
    except click.ClickException as e:
        logger.error('cli_error', error=str(e))
        raise SystemExit(e.exit_code)
    except ValueError as e:
        logger.error('validation_error', error=str(e))
        raise SystemExit(3)
    except yt_dlp.utils.DownloadError as e:
        logger.error('download_error', error=str(e))
        raise SystemExit(2)
    except Exception as e:
        logger.exception('unhandled_exception', error=str(e))
        raise SystemExit(1)
