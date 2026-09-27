#!/usr/bin/env python3
"""
strip_audio.py -- drop this script in a folder of .mp4/.mov clips and run it.

It does three things, all in that same folder:

  1. TRACKS: extracts the audio from every .mp4/.mov to a .wav with the
     SAME filename (take1.mp4 -> take1.wav). Distributor-ready WAV:
     44.1 kHz, 16-bit, stereo.
  2. ALBUM: joins all the track wavs, in filename order, into one
     FULL_ALBUM.wav -- a single-file version for album-style uploads.
  3. CHAPTERS: writes FULL_ALBUM_chapters.txt with YouTube-ready
     "0:00 Title" timestamp lines. Paste them into the video description
     and YouTube splits the upload into chapters -- chapters live in the
     description, not in the file, which is why a text doc is the tool.
     Also writes FULL_ALBUM_chapters.ffmeta (ffmpeg chapter metadata) in
     case you ever want chapters baked into a future m4a/mp4.

Built for video creators and live-performance artists: film the show,
run one command, get release-ready audio.

SETUP -- the script needs an ffmpeg binary, from either:
    * a system ffmpeg install (used automatically if present), or
    * pip install imageio-ffmpeg
      (pure-pip package, no compiler, no admin rights -- ships its own
      static ffmpeg binary; works on old pip / old Python, which is the
      whole point: this runs basically anywhere.)

USAGE:
    python strip_audio.py                  # process the folder the script is in
    python strip_audio.py /path/to/clips   # process a different folder
    python strip_audio.py clip1.mp4 clip2.mov
    python strip_audio.py --dry-run        # preview, change nothing
    python strip_audio.py --no-album       # tracks only, no combined file
    python strip_audio.py --format mp3     # individual tracks as 320k MP3
                                           # (the album file stays WAV)
    python strip_audio.py --number         # prefix tracks: 01_take1.wav, ...
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

VIDEO_EXTS = (".mp4", ".mov")
ALBUM_BASENAME = "FULL_ALBUM"


def find_ffmpeg():
    """Return a usable ffmpeg executable path, or None."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except ImportError:
        pass
    return None


def has_audio_stream(ffmpeg, path):
    """True if `ffmpeg -i` reports an audio stream in the file."""
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return "Audio:" in proc.stderr


def get_duration(ffmpeg, path):
    """Duration in seconds (float), parsed from `ffmpeg -i` stderr."""
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", proc.stderr)
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def fmt_timestamp(sec):
    """YouTube-style timestamp: M:SS, or H:MM:SS past an hour."""
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    mnt, s = divmod(rem, 60)
    if h:
        return "%d:%02d:%02d" % (h, mnt, s)
    return "%d:%02d" % (mnt, s)


def collect_inputs(paths):
    """Expand files/dirs into a sorted, de-duplicated list of video files."""
    if not paths:
        # No args: process the folder this script was dropped in.
        paths = [os.path.dirname(os.path.abspath(__file__))]
    files = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                full = os.path.join(p, name)
                if os.path.isfile(full) and name.lower().endswith(VIDEO_EXTS):
                    files.append(full)
        elif os.path.isfile(p):
            files.append(p)
        else:
            print("  ! not found, skipping: %s" % p)
    seen = set()
    ordered = []
    for f in sorted(files):
        if f not in seen:
            seen.add(f)
            ordered.append(f)
    return ordered


def extract_tracks(ffmpeg, files, outdir, args):
    """Extract one audio file per video. Returns [(wav_path, title)] in order."""
    ext = ".wav" if args.format == "wav" else ".mp3"
    pad = max(2, len(str(len(files))))
    tracks = []
    ok = skipped = failed = 0
    for i, src in enumerate(files, 1):
        stem = os.path.splitext(os.path.basename(src))[0]
        base = "%0*d_%s" % (pad, i, stem) if args.number else stem
        dest = os.path.join(outdir, base + ext)
        tag = "[%d/%d]" % (i, len(files))

        if os.path.exists(dest) and not args.overwrite and not args.dry_run:
            print("%s SKIP (exists, use --overwrite): %s"
                  % (tag, os.path.basename(dest)))
            skipped += 1
            tracks.append((dest, stem))
            continue
        if args.dry_run:
            print("%s WOULD EXTRACT: %s -> %s" % (tag, src, dest))
            tracks.append((dest, stem))
            continue
        if not has_audio_stream(ffmpeg, src):
            print("%s SKIP (no audio stream): %s" % (tag, src))
            skipped += 1
            continue

        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error",
               "-y", "-i", src, "-vn",
               "-ar", str(args.sr), "-ac", str(args.ch)]
        if args.format == "wav":
            cmd += ["-c:a", "pcm_s16le", dest]
        else:
            cmd += ["-c:a", "libmp3lame", "-b:a", args.mp3_bitrate, dest]

        if subprocess.run(cmd).returncode == 0 and os.path.isfile(dest):
            print("%s OK: %s" % (tag, os.path.basename(dest)))
            ok += 1
            tracks.append((dest, stem))
        else:
            print("%s FAILED: %s" % (tag, src))
            failed += 1

    print("tracks: %d extracted, %d skipped, %d failed" % (ok, skipped, failed))
    return tracks, failed


def build_album(ffmpeg, tracks, outdir, args):
    """Join tracks into FULL_ALBUM.wav + chapter docs. Returns failure count."""
    if not tracks:
        print("album: nothing to join (no tracks).")
        return 0

    album_wav = os.path.join(outdir, ALBUM_BASENAME + ".wav")
    chapters_txt = os.path.join(outdir, ALBUM_BASENAME + "_chapters.txt")
    chapters_meta = os.path.join(outdir, ALBUM_BASENAME + "_chapters.ffmeta")

    if args.dry_run:
        print("WOULD BUILD: %s  (+ chapters txt/ffmeta)" % album_wav)
        return 0
    if os.path.exists(album_wav) and not args.overwrite:
        print("album: SKIP (exists, use --overwrite): %s"
              % os.path.basename(album_wav))
        return 0

    # Chapter timestamps from the real durations of the finished track files.
    starts = []
    pos = 0.0
    durations = []
    for wav, _title in tracks:
        starts.append(pos)
        d = get_duration(ffmpeg, wav)
        durations.append(d)
        pos += d
    total = pos

    with open(chapters_txt, "w") as f:
        f.write("# %s chapters -- paste the timestamp lines into the YouTube\n"
                "# video description and YouTube will split it into chapters.\n"
                "# (YouTube wants the first line at 0:00 and at least 3 chapters.)\n"
                "# Total runtime: %s\n" % (ALBUM_BASENAME, fmt_timestamp(total)))
        for (wav, title), start in zip(tracks, starts):
            f.write("%s %s\n" % (fmt_timestamp(start), title))

    with open(chapters_meta, "w") as f:
        f.write(";FFMETADATA1\ntitle=%s\n" % ALBUM_BASENAME)
        for (wav, title), start, d in zip(tracks, starts, durations):
            f.write("[CHAPTER]\nTIMEBASE=1/1000\nSTART=%d\nEND=%d\ntitle=%s\n"
                    % (int(start * 1000), int((start + d) * 1000), title))

    list_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                         delete=False) as lf:
            for wav, _title in tracks:
                lf.write("file '%s'\n" % wav.replace("'", "'\\''"))
            list_path = lf.name
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
               "-f", "concat", "-safe", "0", "-i", list_path,
               "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", album_wav]
        rc = subprocess.run(cmd).returncode
    finally:
        if list_path and os.path.exists(list_path):
            os.unlink(list_path)

    if rc == 0 and os.path.isfile(album_wav):
        print("album: OK: %s (%s, %d chapters)" %
              (os.path.basename(album_wav), fmt_timestamp(total), len(tracks)))
        print("chapters: %s , %s" %
              (os.path.basename(chapters_txt), os.path.basename(chapters_meta)))
        return 0
    print("album: FAILED: %s" % album_wav)
    return 1


def main():
    ap = argparse.ArgumentParser(
        description="Extract audio from .mp4/.mov clips, join into one album "
                    "file, and write YouTube chapter docs.")
    ap.add_argument("inputs", nargs="*",
                    help="video files and/or directories "
                         "(default: the folder this script is in)")
    ap.add_argument("-o", "--out", default=None,
                    help="output directory (default: same folder as the videos)")
    ap.add_argument("--format", choices=["wav", "mp3"], default="wav",
                    help="individual track format (default: wav; album stays WAV)")
    ap.add_argument("--sr", type=int, default=44100,
                    help="track sample rate in Hz (default: 44100)")
    ap.add_argument("--ch", type=int, default=2, choices=[1, 2],
                    help="track channels: 1 = mono, 2 = stereo (default: 2)")
    ap.add_argument("--mp3-bitrate", default="320k",
                    help="MP3 bitrate for --format mp3 (default: 320k)")
    ap.add_argument("--number", action="store_true",
                    help="prefix track numbers: 01_take1.wav, ...")
    ap.add_argument("--no-album", action="store_true",
                    help="skip the combined FULL_ALBUM.wav + chapter docs")
    ap.add_argument("--overwrite", action="store_true",
                    help="re-extract / rebuild even if outputs already exist")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would happen without doing it")
    args = ap.parse_args()

    ffmpeg = find_ffmpeg()
    if not ffmpeg and not args.dry_run:
        sys.exit(
            "ERROR: no ffmpeg found.\n"
            "  - install ffmpeg with your system package manager, or\n"
            "  - run:  pip install imageio-ffmpeg   "
            "(ships its own ffmpeg binary, no admin needed)"
        )
    if args.dry_run and not ffmpeg:
        print("(dry run: no ffmpeg found, but none needed to preview)")

    files = collect_inputs(args.inputs)
    if not files:
        sys.exit("No .mp4/.mov files found in the given inputs.")

    outdir = args.out or os.path.dirname(os.path.abspath(files[0]))
    os.makedirs(outdir, exist_ok=True)
    print("input: %d video file(s) -> %s" % (len(files), outdir))

    tracks, track_failed = extract_tracks(ffmpeg, files, outdir, args)

    album_failed = 0
    if not args.no_album:
        album_failed = build_album(ffmpeg, tracks, outdir, args)

    failed = track_failed + album_failed
    print("\nDone -> %s" % outdir)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
