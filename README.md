# ytd — YouTube Downloader CLI

A command-line tool for downloading videos and playlists from YouTube with automatic format selection, subtitle embedding, thumbnail embedding, and structured logging.

## Features

- **Smart URL detection** — automatically distinguishes between single videos and playlists and applies the appropriate output template
- **Best quality selection** — picks the best available video stream combined with Russian and/or English audio tracks, falling back gracefully
- **Rich post-processing** — embeds subtitles (`ru`, `en`), thumbnails, chapters, and metadata directly into the output file
- **MKV/MP4 output** — merges streams into a container that preserves all embedded data
- **Resumable downloads** — continues interrupted downloads and retries failed fragments automatically
- **Structured logging** — outputs human-readable logs to stdout and JSON logs to a rotating `ytd.log` file in the working directory
- **Cookie support** — accepts a Netscape-formatted cookies file for authenticated or age-restricted content

## Requirements

- Python 3.10+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [FFmpeg](https://ffmpeg.org/) (must be available in `PATH`)
- Python packages: `yt-dlp`, `structlog`, `typer`

Install dependencies:

```bash
pip install yt-dlp structlog typer
```

## Usage

```bash
python ./src/ytd/main.py <URL> [OPTIONS]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `URL` | The YouTube URL to download (video, short, live stream, or playlist) |

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--cookies PATH` | Path to a Netscape-formatted cookies file | _(none)_ |

### Examples

Download a single video:
```bash
python ./src/ytd/main.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

Download a playlist:
```bash
python ./src/ytd/main.py https://www.youtube.com/playlist?list=PLxxxxxx
```

Download with a cookies file (for members-only or age-restricted content):
```bash
python ./src/ytd/main.py https://www.youtube.com/watch?v=dQw4w9WgXcQ --cookies cookies.txt
```

## Output Structure

**Single video:**
```
<Channel Name> - <Video Title>.<ext>
```

**Playlist:**
```
<Channel Name> - <Playlist Title>/
    001 - <Video Title>.<ext>
    002 - <Video Title>.<ext>
    ...
```

## Logging

The tool writes logs to two destinations simultaneously:

| Destination | Format | Level |
|-------------|--------|-------|
| `stdout` | Human-readable (colored when TTY) | `INFO` and above |
| `stderr` | Human-readable | `ERROR` and above |
| `ytd.log` (cwd) | JSON, rotating (10 MB × 7 backups) | `INFO` and above |

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Unhandled exception |
| `2` | yt-dlp download error |
| `3` | Validation error (e.g. invalid URL) |

## Supported URL Formats

The tool accepts any URL belonging to the following domains (including subdomains such as `www.`, `m.`, `music.`):

- `youtube.com` — `/watch`, `/shorts/`, `/live/`, `/playlist`
- `youtu.be` — short links (always treated as single videos)