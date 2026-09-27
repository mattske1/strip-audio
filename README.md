# strip-audio

One script, one command: turn a folder of `.mp4` / `.mov` clips into
release-ready audio.

Built for **video creators and live-performance artists** — film the show,
run the script, get audio you can actually release.

## What it does

Drop `strip_audio.py` in a folder of clips and run it with no arguments:

```
python strip_audio.py
```

It produces, in that same folder:

1. **TRACKS** — the audio from every clip, extracted to a `.wav` with the
   same filename (`take1.mp4` → `take1.wav`). Distributor-ready:
   44.1 kHz, 16-bit, stereo. Upload these straight to your distributor.
2. **ALBUM** — all tracks joined in filename order into `FULL_ALBUM.wav`,
   a single-file version for album-style uploads.
3. **CHAPTERS** — `FULL_ALBUM_chapters.txt` with YouTube-ready `0:00 Title`
   timestamp lines. Paste them into the video description and YouTube
   splits the upload into chapters. Also writes `FULL_ALBUM_chapters.ffmeta`
   (ffmpeg chapter metadata) if you ever want chapters baked into a file.

## Setup

The script needs an ffmpeg binary — either:

- a system ffmpeg install (used automatically if present), or
- `pip install imageio-ffmpeg` — a pure-pip package (no compiler, no admin
  rights) that ships its own static ffmpeg binary. Works on old pip and old
  Python versions, which is the whole point: this runs basically anywhere.

## Usage

```
python strip_audio.py                  # process the folder the script is in
python strip_audio.py /path/to/clips   # process a different folder
python strip_audio.py clip1.mp4 clip2.mov
python strip_audio.py --dry-run        # preview, change nothing
python strip_audio.py --no-album       # tracks only, no combined file
python strip_audio.py --format mp3     # individual tracks as 320k MP3
                                       # (the album file stays WAV)
python strip_audio.py --number         # prefix tracks: 01_take1.wav, ...
python strip_audio.py --overwrite      # re-extract even if outputs exist
```

Files are processed in sorted filename order, so name your clips in the
order you want the tracks (`01_opener.mp4`, `02_main.mp4`, …) or pass
`--number` and let the script do it.

## Notes

- Directories are scanned non-recursively for `.mp4` / `.mov`
  (case-insensitive). Clips with no audio stream are skipped with a warning.
- Existing outputs are skipped unless you pass `--overwrite`.

## License

MIT — see [LICENSE](LICENSE).
