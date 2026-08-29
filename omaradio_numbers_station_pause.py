#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "kokoro-onnx",
#     "soundfile",
#     "numpy",
# ]
# ///
"""
OmaRadio "Numbers Station" Segment Generator
=============================================

Builds a two-part audio segment for OmaRadio Prime:

  1. A plain-spoken test announcement.
  2. A "numbers station" style encoded message -- the eerie, digit-by-digit
     shortwave transmission style real pirate/spy stations have used since
     the Cold War. It's built from a simple, fully reversible substitution
     cipher, so listeners (or DJs) who want to "crack the code" can decode
     it by hand or by re-running this script with --decode.

By default the rendered audio is also run through a shortwave-radio effect
(bandpass EQ, static bed, carrier whistle, fading/flutter, bit-crushing --
see RADIO_PRESETS) via an ffmpeg filter chain. Use --degrade none for a
clean, dry take instead.

This is NOT cryptographically secure and isn't meant to be -- the whole
point of a numbers-station bit is that it's crackable with a pencil and a
bit of patience, same as the real thing.

Usage:
    python3 omaradio_numbers_station.py                     # cipher only, no audio
    python3 omaradio_numbers_station.py --audio              # render .wav, "classic" radio effect
    python3 omaradio_numbers_station.py --audio --degrade none        # clean, undegraded take
    python3 omaradio_numbers_station.py --audio --degrade heavy       # barely-legible static mess
    python3 omaradio_numbers_station.py --audio --format mp3          # render .mp3 instead
    python3 omaradio_numbers_station.py --audio --format both         # render both
    python3 omaradio_numbers_station.py --audio --voice bm_george     # different Kokoro voice
    python3 omaradio_numbers_station.py --list-voices                 # show all available voices
    python3 omaradio_numbers_station.py --decode "00 19 12"           # decode a group string and exit
    python3 omaradio_numbers_station.py --spy-phonetics --audio       # NATO-telephony digit words
    python3 omaradio_numbers_station.py --message-file other.txt --write-encoded encoded.txt

The announcement and hidden-message copy live in plain text files, not in
this script -- edit them freely without touching any code:

    announcement.txt   spoken as-is, right at the top of the broadcast
    message.txt        run through the cipher and spoken as the two
                        message passes

Both default to living next to this script (not the working directory) and
are created automatically with today's default copy the first time you run
this with no --announcement-file/--message-file override, so a fresh
checkout works with zero setup. Point --announcement-file / --message-file
at different files to use custom copy instead -- an explicit path is
expected to already exist and errors clearly if it doesn't, rather than
silently falling back to the default.

Characters outside the cipher's supported set (see CHARSET below) are
silently replaced with '#' when encoding message.txt -- no warning, so a
stray character just becomes a '#' in the broadcast rather than stopping
the script. --write-encoded PATH saves the resulting digit-groups string
to a plain text file, in the same format --decode reads back in.

Dependencies (only needed for --audio): kokoro-onnx, soundfile, numpy.
The radio effect and --format mp3/both need ffmpeg on PATH (see below) --
no extra Python packages either way.

Recommended -- run it with uv and skip installing anything by hand. The
block at the top of this file is PEP 723 inline script metadata; `uv run`
reads it and builds a throwaway venv with the right deps automatically:

    uv run omaradio_numbers_station.py --audio
    uv run omaradio_numbers_station.py --audio --format mp3

(Optional: `chmod +x` this file with the shebang changed to
`#!/usr/bin/env -S uv run --script` and you can just do
`./omaradio_numbers_station.py --audio` directly.)

Manual uv install, if you'd rather keep a persistent environment:
    uv venv && uv pip install kokoro-onnx soundfile numpy
    # or, inside a uv-managed project:
    uv add kokoro-onnx soundfile numpy

Plain pip fallback:
    pip install kokoro-onnx soundfile numpy --break-system-packages

Kokoro model weights -- a SEPARATE one-time download, not something uv/pip
install for you (they only install the Python package, not the ~325 MB of
model binaries). Run once, in the same directory as this script (or pass
--model / --voices to point elsewhere):

    wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
    wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

Release asset names occasionally change upstream -- if those 404, check
https://github.com/thewh1teagle/kokoro-onnx for the current filenames.
Running --audio with either file missing prints this same guidance instead
of a raw traceback.

ffmpeg (radio effect AND mp3 output) -- also not a Python package, so
uv/pip can't install it either:
    Ubuntu / the droplet:  sudo apt install ffmpeg
    Omarchy / Arch:        sudo pacman -S ffmpeg
"""

import argparse
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. On-air copy -- loaded from plain text files (see --announcement-file /
# --message-file), not hardcoded, so the copy can change without touching
# this script. The strings below are SEED content only: used to bootstrap
# the default files on first run, never read directly at broadcast time.
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ANNOUNCEMENT_FILE = SCRIPT_DIR / "announcement.txt"
DEFAULT_MESSAGE_FILE = SCRIPT_DIR / "message.txt"

_SEED_ANNOUNCEMENT = (
    "This is a test of the OmaRadio broadcast network! "
    "Transmitter-One broadcasting at 100 KiloWatts. "
    "It's Omaachee, BTW!"
)

_SEED_MESSAGE = (
    "Download Omarchy Linux at http://omarchy.org and soak up a "
    "Beautiful, Modern & Opinionated Linux by DHH."
)


def load_text_content(path: Path, seed: str, is_default_path: bool, label: str) -> str:
    """
    Reads plain text from `path`, collapsing all whitespace (including line
    breaks) to single spaces -- both so multi-line files read naturally as
    TTS input, and so a stray newline in message.txt doesn't hit the
    cipher's unsupported-character fallback.

    If `path` doesn't exist:
      - and it IS one of the default files, bootstrap it with `seed`
        content and continue, so a fresh checkout works with no setup.
      - and it's a custom path the person explicitly passed, fail loudly
        instead -- an explicit --file argument implies it should already
        exist, so silently substituting default copy would be surprising.
    """
    if not path.exists():
        if is_default_path:
            path.write_text(seed + "\n", encoding="utf-8")
            print(f"[+] Created default {label.lower()} file: {path}")
        else:
            print(f"[!] {label} file not found: {path}")
            print(f"    Create it (plain text, UTF-8), or drop the --*-file flag to use the default.")
            raise SystemExit(1)

    return " ".join(path.read_text(encoding="utf-8").split())


# ---------------------------------------------------------------------------
# 2. The cipher -- a simple, symmetric character <-> 2-digit substitution
# ---------------------------------------------------------------------------

CHARSET = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,:/&'!-"
CODE_OF = {ch: f"{i:02d}" for i, ch in enumerate(CHARSET)}
CHAR_OF = {v: k for k, v in CODE_OF.items()}
FALLBACK_CODE = f"{len(CHARSET):02d}"  # unused index -> marks any stray character
CHAR_OF[FALLBACK_CODE] = "#"


def encode(text: str) -> str:
    """Plaintext -> raw digit string (no grouping yet)."""
    return "".join(CODE_OF.get(ch, FALLBACK_CODE) for ch in text.upper())


def group(digits: str, size: int = 5) -> str:
    """Raw digits -> classic 5-digit spoken groups, e.g. '00191 20301 ...'"""
    return " ".join(digits[i:i + size] for i in range(0, len(digits), size))


def decode(grouped: str) -> str:
    """Spoken groups (or raw digits) -> plaintext."""
    digits = grouped.replace(" ", "")
    return "".join(CHAR_OF.get(digits[i:i + 2], "#") for i in range(0, len(digits), 2))


def charset_projection(text: str) -> str:
    """
    What decode(group(encode(text))) will actually produce: uppercase, with
    any character outside CHARSET silently replaced by '#' -- the same
    fallback encode() already applies. Used to sanity-check the round trip
    without falsely failing on message.txt content that includes characters
    the cipher doesn't support (which are substituted, not rejected).
    """
    return "".join(ch if ch in CODE_OF else "#" for ch in text.upper())


# ---------------------------------------------------------------------------
# 3. Digit words for TTS -- plain, or old-school "spy phonetics"
# ---------------------------------------------------------------------------

DIGIT_WORDS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}

# The ICAO/telephony digit variants long associated with real numbers
# stations -- chosen for being unambiguous over noisy shortwave audio.
SPY_DIGIT_WORDS = {
    "0": "nadazero", "1": "unaone", "2": "bissotwo", "3": "terrathree",
    "4": "kartefour", "5": "pantafive", "6": "soxisix", "7": "setteseven",
    "8": "oktoeight", "9": "novenine",
}


def digits_to_words(digit_str: str, spy_phonetics: bool = False) -> str:
    words = SPY_DIGIT_WORDS if spy_phonetics else DIGIT_WORDS
    return " ".join(words[d] for d in digit_str)


def spoken_groups(grouped: str, spy_phonetics: bool = False) -> str:
    """'00191 20301' -> 'zero zero one nine one, two zero three zero one'"""
    return ", ".join(digits_to_words(block, spy_phonetics) for block in grouped.split(" "))


# ---------------------------------------------------------------------------
# 4. Build the full on-air script for the numbers-station segment
# ---------------------------------------------------------------------------

@dataclass
class PacedSpeech:
    """
    A message-pass payload: kokoro speaks it one digit word at a time (not
    as one long string) so a configurable pause can be inserted between
    each word, at a configurable speed -- both scoped to message passes
    only, independent of the announcement/attention/sign-off lines.
    `text` is kept for display (it's the same joined string spoken_groups()
    always produced); render_audio() re-splits it into words at render time.
    """
    text: str
    speed: float
    digit_pause: float


def build_broadcast_script(announcement: str, hidden_message: str, spy_phonetics: bool = False,
                            tone_freq: float = 1000.0, tone_duration: float = 1.5,
                            tone_at=("interval", "pass-break", "signoff"),
                            message_speed: float = 0.85, digit_pause: float = 0.15):
    """
    Returns (script, grouped) where script is a list of (label, kind, payload)
    triples in broadcast order:
      kind == "speech"       -> payload is text for kokoro to speak normally
      kind == "speech_paced" -> payload is a PacedSpeech (message passes only)
      kind == "tone"         -> payload is (frequency_hz, duration_s) for a
                                 generated marker tone (no TTS involved)

    announcement is spoken as-is. hidden_message is run through the cipher
    (encode -> group) before being spoken as the two message passes -- see
    load_text_content() for where these normally come from (announcement.txt
    / message.txt).

    tone_at controls which of the three marker-tone slots are included:
      "interval"   -- before the message starts (classic numbers-station
                       interval signal, marking the switch into cipher mode)
      "pass-break" -- between the two repeated group passes
      "signoff"    -- after "End of message", marking end of transmission
    Pass an empty tone_at to disable marker tones entirely.

    message_speed is kokoro's speed multiplier applied ONLY to the two
    message passes (1.0 = normal; lower = slower). digit_pause is the
    silence, in seconds, inserted between each spoken digit word within a
    message pass (0 disables it). Neither affects the announcement,
    attention line, or sign-off, which stay at the standard pace.
    """
    grouped = group(encode(hidden_message), size=5)
    n_groups = len(grouped.split(" "))
    count_spoken = digits_to_words(f"{n_groups:03d}", spy_phonetics)
    message_spoken = spoken_groups(grouped, spy_phonetics)
    tone = (tone_freq, tone_duration)
    paced_message = PacedSpeech(message_spoken, message_speed, digit_pause)

    script = [("announcement", "speech", announcement)]
    if "interval" in tone_at:
        script.append(("interval_signal", "tone", tone))
    script.append(("attention", "speech", f"Attention. Attention. Message contains {count_spoken} groups."))
    script.append(("message_pass_1", "speech_paced", paced_message))
    if "pass-break" in tone_at:
        script.append(("pass_break", "tone", tone))
    script.append(("message_pass_2", "speech_paced", paced_message))
    script.append(("sign_off", "speech", "End of message. End of transmission."))
    if "signoff" in tone_at:
        script.append(("end_tone", "tone", tone))

    return script, grouped


# ---------------------------------------------------------------------------
# 5. Kokoro v1.0 voices -- for --voice / --list-voices
#
# Prefix legend: 1st letter = language, 2nd = gender (f = female, m = male).
#   a = American English    b = British English   e = European Spanish
#   f = French              h = Hindi              i = Italian
#   j = Japanese            p = Brazilian Portuguese   z = Mandarin Chinese
#
#   American English (af/am):
#     af_alloy, af_aoede, af_bella, af_heart, af_jessica, af_kore,
#     af_nicole, af_nova, af_river, af_sarah, af_sky,
#     am_adam, am_echo, am_eric, am_fenrir, am_liam, am_michael,
#     am_onyx, am_puck, am_santa
#   British English (bf/bm):
#     bf_alice, bf_emma, bf_isabella, bf_lily,
#     bm_daniel, bm_fable, bm_george, bm_lewis
#   European Spanish (ef/em):     ef_dora | em_alex, em_santa
#   French (ff):                  ff_siwis
#   Hindi (hf/hm):                hf_alpha, hf_beta | hm_omega, hm_psi
#   Italian (if/im):              if_sara | im_nicola
#   Japanese (jf/jm):             jf_alpha, jf_gongitsune, jf_nezumi,
#                                  jf_tebukuro | jm_kumo
#   Brazilian Portuguese (pf/pm): pf_dora | pm_alex, pm_santa
#   Mandarin Chinese (zf/zm):     zf_xiaobei, zf_xiaoni, zf_xiaoxiao,
#                                  zf_xiaoyi | zm_yunjian, zm_yunxi,
#                                  zm_yunxia, zm_yunyang
#
# 54 voices total. OmaRadio's copy is English -- stick to af_*/am_*/bf_*/bm_*
# unless you're deliberately doing a multilingual bit; other voices need a
# matching --lang (auto-guessed below from the voice prefix, override if it
# sounds wrong). This list and the lang-code guesses are pieced together
# from public examples rather than one authoritative source doc, so treat
# them as best-effort -- check https://github.com/thewh1teagle/kokoro-onnx
# if a voice 404s or a non-English lang tag mispronounces.
# ---------------------------------------------------------------------------

VOICES_BY_LANG = {
    "American English": ("a", [
        "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore",
        "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
        "am_onyx", "am_puck", "am_santa",
    ]),
    "British English": ("b", [
        "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
        "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    ]),
    "European Spanish": ("e", ["ef_dora", "em_alex", "em_santa"]),
    "French": ("f", ["ff_siwis"]),
    "Hindi": ("h", ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"]),
    "Italian": ("i", ["if_sara", "im_nicola"]),
    "Japanese": ("j", ["jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo"]),
    "Brazilian Portuguese": ("p", ["pf_dora", "pm_alex", "pm_santa"]),
    "Mandarin Chinese": ("z", [
        "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
        "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
    ]),
}

# voice-prefix letter -> kokoro-onnx `lang` argument (best-effort, see note above)
LANG_HINT_BY_PREFIX = {
    "a": "en-us", "b": "en-gb", "e": "es", "f": "fr-fr", "h": "hi",
    "i": "it", "j": "ja", "p": "pt-br", "z": "cmn",
}


def print_voice_list():
    print("Kokoro v1.0 voices -- 54 total across 9 languages")
    print("Prefix legend: 1st letter = language, 2nd = gender (f/m)\n")
    for lang_name, (prefix, voices) in VOICES_BY_LANG.items():
        lang_tag = LANG_HINT_BY_PREFIX.get(prefix, "?")
        print(f"{lang_name}  (--lang {lang_tag}, auto-picked from prefix '{prefix}')")
        print("  " + ", ".join(voices))
        print()
    print("OmaRadio's copy is English -- stick to af_*/am_*/bf_*/bm_* unless")
    print("you're deliberately doing a multilingual bit.")


# ---------------------------------------------------------------------------
# 6. "Shortwave" degradation effect -- ffmpeg filter chain, no extra deps
#
# hp/lp        = bandpass edges in Hz (the single biggest factor in the
#                "sounds like radio, not a podcast" effect)
# noise_db     = static-bed level, relative to full scale (more negative = quieter)
# tone_db/hz   = faint carrier whistle level + pitch (classic numbers-station touch)
# trem_hz/d    = tremolo (amplitude wobble) rate/depth -- simulates selective fading
# vib_hz/d     = vibrato (pitch wobble) rate/depth -- simulates ionospheric flutter
# crush_bits   = bit-depth reduction via ffmpeg's acrusher (None = skip)
# comp         = whether to squash dynamics with acompressor, like an old transmitter
# ---------------------------------------------------------------------------

RADIO_PRESETS = {
    "light": dict(hp=300, lp=3400, noise_db=-40, tone_db=-46, tone_hz=850,
                  trem_hz=0.2, trem_d=0.12, vib_hz=0.4, vib_d=0.04,
                  crush_bits=None, comp=False),
    "classic": dict(hp=300, lp=3000, noise_db=-30, tone_db=-36, tone_hz=900,
                     trem_hz=0.3, trem_d=0.30, vib_hz=0.5, vib_d=0.12,
                     crush_bits=10, comp=True),
    "heavy": dict(hp=400, lp=2600, noise_db=-22, tone_db=-30, tone_hz=950,
                  trem_hz=0.45, trem_d=0.50, vib_hz=0.7, vib_d=0.25,
                  crush_bits=7, comp=True),
}


def _radio_filter_complex(p: dict) -> str:
    """Builds the ffmpeg -filter_complex graph string for one preset's params."""
    voice_chain = [f"highpass=f={p['hp']}", f"lowpass=f={p['lp']}"]
    if p["comp"]:
        voice_chain.append("acompressor=threshold=-18dB:ratio=4:attack=5:release=80")
    voice_chain.append(f"tremolo=f={p['trem_hz']}:d={p['trem_d']}")
    voice_chain.append(f"vibrato=f={p['vib_hz']}:d={p['vib_d']}")
    if p["crush_bits"]:
        voice_chain.append(f"acrusher=bits={p['crush_bits']}:mode=log:aa=1")
    voice_chain_str = ",".join(voice_chain)

    return (
        f"[0:a]{voice_chain_str}[voice];"
        f"[1:a]volume={p['noise_db']}dB[noise];"
        f"[2:a]volume={p['tone_db']}dB[tone];"
        f"[voice][noise][tone]amix=inputs=3:duration=first:dropout_transition=0:normalize=0,"
        f"aformat=channel_layouts=mono[out]"
    )


def apply_radio_effect(in_wav: str, out_wav: str, sample_rate: int, preset: str = "classic") -> bool:
    """
    Runs a dry voice .wav through an ffmpeg filter chain to make it sound
    like a shortwave/numbers-station transmission: bandpass-filtered voice
    mixed with a static noise bed and a faint carrier whistle, plus slow
    amplitude "fading" (tremolo), pitch "flutter" (vibrato), and optional
    bit-crushing. Returns True if out_wav was written; False means the
    caller should fall back to using in_wav as-is.
    """
    params = RADIO_PRESETS.get(preset)
    if params is None:
        print(f"[!] Unknown --degrade preset '{preset}' -- leaving audio undegraded.")
        return False

    if shutil.which("ffmpeg") is None:
        print("[!] ffmpeg not found on PATH -- can't apply the radio effect.")
        print("    Ubuntu / the droplet:  sudo apt install ffmpeg")
        print("    Omarchy / Arch:        sudo pacman -S ffmpeg")
        return False

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", in_wav,
        "-f", "lavfi", "-i", f"anoisesrc=color=pink:sample_rate={sample_rate}:amplitude=1",
        "-f", "lavfi", "-i", f"sine=frequency={params['tone_hz']}:sample_rate={sample_rate}",
        "-filter_complex", _radio_filter_complex(params),
        "-map", "[out]",
        out_wav,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[!] ffmpeg failed to apply the radio effect: {result.stderr.strip()}")
        return False

    print(f"[+] Applied '{preset}' radio effect -> {out_wav}")
    return True


# ---------------------------------------------------------------------------
# 7. mp3 transcode -- ffmpeg, same tool the radio effect already needs
# ---------------------------------------------------------------------------

def wav_to_mp3(wav_path: str, mp3_path: str, bitrate: str = "192k") -> bool:
    """Shell out to ffmpeg to transcode wav -> mp3. Returns True on success."""
    if shutil.which("ffmpeg") is None:
        print("[!] ffmpeg not found on PATH -- can't create mp3.")
        print("    Ubuntu / the droplet:  sudo apt install ffmpeg")
        print("    Omarchy / Arch:        sudo pacman -S ffmpeg")
        return False

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", wav_path,
        "-codec:a", "libmp3lame", "-b:a", bitrate,
        mp3_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[!] ffmpeg failed to create mp3: {result.stderr.strip()}")
        return False

    print(f"[+] Wrote {mp3_path}")
    return True


def _check_model_files(model_path: str, voices_path: str) -> bool:
    """
    Pre-flight check so a missing Kokoro model/voices file produces a clear,
    actionable message instead of a raw onnxruntime traceback. uv/pip only
    install the *Python package* (kokoro-onnx) -- the model weights are a
    separate, one-time binary download that neither tool handles for you.
    """
    missing = [p for p in (model_path, voices_path) if not Path(p).exists()]
    if not missing:
        return True

    print(f"[!] Missing Kokoro model file(s): {', '.join(missing)}")
    print("    These are a one-time ~325 MB download, separate from the pip/uv package:")
    print("      wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx")
    print("      wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin")
    print("    Then either move them into this directory, or point at them with:")
    print("      --model /path/to/kokoro-v1.0.onnx --voices /path/to/voices-v1.0.bin")
    print("    (Release asset names occasionally change upstream -- if those 404,")
    print("     check https://github.com/thewh1teagle/kokoro-onnx for current filenames.)")
    return False


# ---------------------------------------------------------------------------
# 8. Definable marker tones -- pure numpy, no TTS or ffmpeg involved
# ---------------------------------------------------------------------------

def generate_tone(frequency: float, duration: float, sample_rate: int,
                   amplitude: float = 0.5, fade_ms: float = 8.0):
    """
    A sine wave at `frequency` Hz for `duration` seconds, with a short
    linear fade in/out (default 8ms) so it doesn't click/pop at the edges
    when concatenated next to speech. Returns a float32 numpy array.
    """
    import numpy as np

    n = max(int(sample_rate * duration), 1)
    t = np.arange(n) / sample_rate
    tone = (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)

    fade_n = min(int(sample_rate * fade_ms / 1000), n // 2)
    if fade_n > 0:
        tone[:fade_n] *= np.linspace(0, 1, fade_n, dtype=np.float32)
        tone[-fade_n:] *= np.linspace(1, 0, fade_n, dtype=np.float32)

    return tone


# ---------------------------------------------------------------------------
# 9. Optional audio rendering via kokoro-onnx, with radio effect + wav/mp3 output
# ---------------------------------------------------------------------------

def render_audio(script, out_stem="omaradio_numbers_station", formats=("wav",),
                  model_path="kokoro-v1.0.onnx", voices_path="voices-v1.0.bin",
                  voice="af_sarah", lang="en-us", mp3_bitrate="192k",
                  degrade="classic", keep_dry=False):
    """
    Renders each script entry -- speech via kokoro-onnx, tones via
    generate_tone() -- concatenates them with a short silence in between,
    optionally runs the result through the shortwave radio effect (see
    RADIO_PRESETS), and writes .wav, .mp3, or both (mp3 is produced by
    transcoding via ffmpeg). Adjust model_path / voices_path / voice / lang
    to match your local Kokoro setup -- this calls kokoro-onnx's typical
    `Kokoro(model, voices).create(text, voice, speed, lang)` interface;
    check your installed version's API if it errors.

    Returns a list of the file paths actually written.
    """
    try:
        import numpy as np
        import soundfile as sf
        from kokoro_onnx import Kokoro
    except ImportError as exc:
        print(f"[!] Audio rendering skipped -- missing dependency: {exc}")
        print("    uv run omaradio_numbers_station.py --audio   (auto-installs deps)")
        print("    or: pip install kokoro-onnx soundfile numpy --break-system-packages")
        return []

    if not _check_model_files(model_path, voices_path):
        return []

    kokoro = Kokoro(model_path, voices_path)
    chunks = []
    pause = None
    sample_rate = 24000  # Kokoro's standard rate; updated as soon as speech renders
    ref_dtype = [None]  # boxed so the nested helper can update it

    def _add(arr):
        if ref_dtype[0] is None:
            ref_dtype[0] = arr.dtype
        else:
            arr = arr.astype(ref_dtype[0], copy=False)
        chunks.append(arr)

    for label, kind, payload in script:
        if kind == "speech":
            samples, sample_rate = kokoro.create(payload, voice=voice, speed=0.95, lang=lang)
            _add(samples)
            print(f"  rendered: {label} ({len(payload)} chars)")

        elif kind == "speech_paced":
            words = payload.text.replace(",", "").split()
            digit_gap = None
            for i, word in enumerate(words):
                w_samples, sample_rate = kokoro.create(word, voice=voice, speed=payload.speed, lang=lang)
                _add(w_samples)
                if payload.digit_pause > 0 and i < len(words) - 1:
                    if digit_gap is None:
                        digit_gap = np.zeros(int(sample_rate * payload.digit_pause), dtype=w_samples.dtype)
                    _add(digit_gap)
            print(f"  rendered: {label} ({len(words)} digit words @ speed={payload.speed}, "
                  f"{payload.digit_pause}s gaps between them)")

        else:  # kind == "tone"
            freq, dur = payload
            samples = generate_tone(freq, dur, sample_rate)
            _add(samples)
            print(f"  rendered: {label} (tone, {freq:g} Hz x {dur:g}s)")

        if pause is None:
            pause = np.zeros(int(sample_rate * 0.6), dtype=ref_dtype[0])
        _add(pause)

    full = np.concatenate(chunks)

    dry_wav = f"{out_stem}_dry.wav"
    sf.write(dry_wav, full, sample_rate)

    final_wav = f"{out_stem}.wav"
    written = []

    if degrade == "none":
        Path(dry_wav).rename(final_wav)
        print(f"[+] Wrote {final_wav}")
    elif apply_radio_effect(dry_wav, final_wav, sample_rate, preset=degrade):
        if keep_dry:
            written.append(dry_wav)
        else:
            Path(dry_wav).unlink(missing_ok=True)
    else:
        # Effect failed (missing ffmpeg, bad preset name) -- fall back to dry.
        Path(dry_wav).rename(final_wav)
        print(f"[+] Wrote {final_wav} (dry -- radio effect unavailable)")

    written.insert(0, final_wav)

    if "mp3" in formats:
        mp3_path = f"{out_stem}.mp3"
        if wav_to_mp3(final_wav, mp3_path, bitrate=mp3_bitrate):
            written.append(mp3_path)

    if "wav" not in formats:
        Path(final_wav).unlink(missing_ok=True)
        written.remove(final_wav)

    return written


# ---------------------------------------------------------------------------
# 10. CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--audio", action="store_true", help="Render audio via kokoro-onnx")
    parser.add_argument("--format", choices=["wav", "mp3", "both"], default="wav",
                         help="Audio output format when --audio is set (mp3 needs ffmpeg)")
    parser.add_argument("--degrade", choices=["none", "light", "classic", "heavy"], default="classic",
                         help="Shortwave radio effect intensity (default: classic). "
                              "'none' renders a clean, undegraded take")
    parser.add_argument("--keep-dry", action="store_true",
                         help="Also save the pre-effect clean take as <out>_dry.wav "
                              "(only relevant when --degrade isn't 'none')")
    parser.add_argument("--tone-freq", type=float, default=1000.0,
                         help="Marker tone frequency in Hz (default: 1000)")
    parser.add_argument("--tone-duration", type=float, default=1.5,
                         help="Marker tone duration in seconds (default: 1.5)")
    parser.add_argument("--tone-at", nargs="*", choices=["interval", "pass-break", "signoff"],
                         default=["interval", "pass-break", "signoff"],
                         help="Where to place the marker tone: interval (before the message), "
                              "pass-break (between the two repeated passes), signoff (after "
                              "'End of message'). Default: all three. Pass --tone-at with no "
                              "values to disable marker tones entirely")
    parser.add_argument("--message-speed", type=float, default=0.85,
                         help="Kokoro speed multiplier for the message passes ONLY (default: "
                              "0.85). 1.0 = normal Kokoro pace. The announcement, attention "
                              "line, and sign-off are unaffected. Going much below ~0.6-0.7 "
                              "tends to sound warbly rather than just slower")
    parser.add_argument("--digit-pause", type=float, default=0.15,
                         help="Silence in seconds between each spoken digit word within a "
                              "message pass (default: 0.15). 0 disables it")
    parser.add_argument("--announcement-file", type=Path, default=DEFAULT_ANNOUNCEMENT_FILE,
                         help=f"Plain text file for the spoken test announcement "
                              f"(default: {DEFAULT_ANNOUNCEMENT_FILE.name}, next to this script -- "
                              f"auto-created with default copy on first run if missing)")
    parser.add_argument("--message-file", type=Path, default=DEFAULT_MESSAGE_FILE,
                         help=f"Plain text file for the hidden message to encode "
                              f"(default: {DEFAULT_MESSAGE_FILE.name}, next to this script -- "
                              f"auto-created with default copy on first run if missing)")
    parser.add_argument("--write-encoded", metavar="PATH", default=None,
                         help="Also write the encoded digit-groups string to this plain text "
                              "file (same format --decode reads back in)")
    parser.add_argument("--spy-phonetics", action="store_true",
                         help="Use nadazero/unaone-style digit words")
    parser.add_argument("--decode", metavar="GROUPS", help="Decode a digit-group string and exit")
    parser.add_argument("--model", default="kokoro-v1.0.onnx",
                         help="Path to the Kokoro .onnx model file (see docstring to download)")
    parser.add_argument("--voices", default="voices-v1.0.bin",
                         help="Path to the Kokoro voices .bin file (see docstring to download)")
    parser.add_argument("--voice", default="af_sarah",
                         help="Kokoro voice ID, e.g. af_sarah (American English female). "
                              "Run --list-voices to see all 54 options")
    parser.add_argument("--lang", default=None,
                         help="kokoro-onnx language tag, e.g. en-us, en-gb. Auto-guessed from "
                              "the --voice prefix if omitted -- override if it sounds wrong")
    parser.add_argument("--list-voices", action="store_true",
                         help="Print all available Kokoro voices, grouped by language, and exit")
    parser.add_argument("--out", default="omaradio_numbers_station",
                         help="Output filename stem, no extension (e.g. 'my_segment')")
    args = parser.parse_args()

    if args.list_voices:
        print_voice_list()
        return

    if args.decode:
        print(decode(args.decode))
        return

    announcement = load_text_content(
        args.announcement_file, _SEED_ANNOUNCEMENT,
        args.announcement_file == DEFAULT_ANNOUNCEMENT_FILE, "Announcement",
    )
    hidden_message = load_text_content(
        args.message_file, _SEED_MESSAGE,
        args.message_file == DEFAULT_MESSAGE_FILE, "Message",
    )

    script, grouped = build_broadcast_script(
        announcement=announcement, hidden_message=hidden_message,
        spy_phonetics=args.spy_phonetics, tone_freq=args.tone_freq,
        tone_duration=args.tone_duration, tone_at=args.tone_at,
        message_speed=args.message_speed, digit_pause=args.digit_pause,
    )

    print("=== Plaintext test announcement ===")
    print(announcement)
    print()
    print("=== Hidden message (plaintext) ===")
    print(hidden_message)
    print()
    print("=== Encoded numbers-station groups ===")
    print(grouped)
    print()

    if args.write_encoded:
        Path(args.write_encoded).write_text(grouped + "\n", encoding="utf-8")
        print(f"[+] Wrote encoded groups -> {args.write_encoded}")
        print()

    print("=== Round-trip decode check ===")
    decoded = decode(grouped)
    print(decoded)
    assert decoded == charset_projection(hidden_message), "Round-trip mismatch -- cipher tables out of sync."
    print("(matches original \u2713)")
    print()

    print("=== Full broadcast script ===")
    for label, kind, payload in script:
        print(f"[{label}]")
        if kind == "speech":
            print(payload)
        elif kind == "speech_paced":
            print(payload.text)
            print(f"  (speed={payload.speed:g}, digit_pause={payload.digit_pause:g}s)")
        else:
            freq, dur = payload
            print(f"<tone: {freq:g} Hz for {dur:g}s>")
        print()

    if args.audio:
        formats = {"wav": ("wav",), "mp3": ("mp3",), "both": ("wav", "mp3")}[args.format]
        out_stem = Path(args.out).stem  # strip any accidental extension the user typed
        lang = args.lang or LANG_HINT_BY_PREFIX.get(args.voice[:1], "en-us")
        render_audio(script, out_stem=out_stem, formats=formats,
                     model_path=args.model, voices_path=args.voices, voice=args.voice,
                     lang=lang, degrade=args.degrade, keep_dry=args.keep_dry)


if __name__ == "__main__":
    main()
