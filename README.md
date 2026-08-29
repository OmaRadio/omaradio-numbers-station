# OmaRadio TX Numbers Station

OmaRadio sometimes operates as a numbers station to send out clandestine messages to Omarchy operatives worldwide. The script can generate the complete broadcast audio including an "Announcement" message, an encoded numbers "Message File", Morse Code encoded message and tones. 

The supplied written text is passed through Kokoro TTS locally which provides the spoken voice audio.

The script provides full parameter control for a number of options and settings.

## Dependencies

**Mandatory python packages required:** `kokoro-onnx, soundfile, numpy`  

The Kokoro model weights are a SEPARATE one-time download. Run this once, in the same directory as this script (or pass
--model / --voices to point elsewhere):

```
    wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
    wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```

If the above 404 errors, check the repo for a new release.

The script will install the python package dependencies on first run if not already installed.

Optional Manual `uv` install, if you'd rather keep a persistent environment: 
`uv venv && uv pip install kokoro-onnx soundfile numpy`

OR, inside a `uv`-managed project:  
`uv add kokoro-onnx soundfile numpy`

**Optional (Recommended and required for audio output):**  
`ffmpeg`

Install via:  
```
Ubuntu / the droplet:  sudo apt install ffmpeg
Omarchy / Arch:        sudo pacman -S ffmpeg
```

## Usage

Via `uv` (Recommended):  

Common usage ...  

Used most often by OmaRadio  
`uv run omaradio_numbers_stations.py --audio --format mp3 --degrade heavy --voice bm_daniel --message-speed 0.93 --digit-pause 0.20`

## Full CLI Reference

Options for `omaradio_numbers_stations.py`...  

Run with `uv run omaradio_numbers_stations.py [flags]` (auto-installs dependencies) or `python3 omaradio_numbers_stations.py [flags]`.

### Full example

All generation flags in one line (excludes `--decode`/`--list-voices`, which are standalone modes that exit before generation — see bottom):

```bash
uv run omaradio_numbers_stations.py --audio --format both --out omaradio_numbers_station --voice af_sarah --lang en-us --model kokoro-v1.0.onnx --voices voices-v1.0.bin --announcement-file announcement.txt --message-file message.txt --morse-file morse.txt --write-encoded encoded.txt --spy-phonetics --degrade classic --keep-dry --tone-freq 1000 --tone-duration 1.5 --tone-at interval pass-break signoff --message-speed 0.85 --digit-pause 0.15 --morse-wpm 18 --morse-freq 600 --morse-break-freq 450 --morse-break-duration 0.8
```

### Content files

| Flag | Default | Description |
|---|---|---|
| `--announcement-file` | `announcement.txt` | Spoken test announcement. Auto-created next to the script on first run. |
| `--message-file` | `message.txt` | Hidden message, run through the numbers-station cipher. Auto-created on first run. |
| `--morse-file` | `morse.txt` | Optional extra message, sent in Morse code. **Not** auto-created — segment is skipped if missing. |
| `--write-encoded` | *(none)* | Also write the encoded digit-groups string to this file. |

### Audio output

| Flag | Default | Description |
|---|---|---|
| `--audio` | off | Render audio via kokoro-onnx (otherwise just prints the script/cipher). |
| `--format` | `wav` | `wav`, `mp3`, or `both`. mp3 requires ffmpeg on PATH. |
| `--out` | `omaradio_numbers_station` | Output filename stem, no extension. |
| `--voice` | `af_sarah` | Kokoro voice ID. Run `--list-voices` for all 54 options. |
| `--lang` | auto | kokoro-onnx language tag. Auto-guessed from the `--voice` prefix if omitted. |
| `--model` | `kokoro-v1.0.onnx` | Path to the Kokoro `.onnx` model file. |
| `--voices` | `voices-v1.0.bin` | Path to the Kokoro voices `.bin` file. |

### Radio effect

| Flag | Default | Description |
|---|---|---|
| `--degrade` | `classic` | Shortwave degradation intensity: `none`, `light`, `classic`, or `heavy`. |
| `--keep-dry` | off | Also save the pre-effect clean take as `<out>_dry.wav`. |

### Marker tones

| Flag | Default | Description |
|---|---|---|
| `--tone-freq` | `1000` | Marker tone frequency, in Hz. |
| `--tone-duration` | `1.5` | Marker tone duration, in seconds. |
| `--tone-at` | `interval pass-break signoff` | Where markers play. Pass with no values to disable entirely. |

### Message pacing

| Flag | Default | Description |
|---|---|---|
| `--message-speed` | `0.85` | Kokoro speed multiplier, applied to the message passes only. |
| `--digit-pause` | `0.15` | Silence, in seconds, between each spoken digit word. |

### Morse code

| Flag | Default | Description |
|---|---|---|
| `--morse-wpm` | `18` | Morse code speed, in words per minute. |
| `--morse-freq` | `600` | Morse code tone frequency, in Hz. |
| `--morse-break-freq` | `450` | Frequency of the break tones framing the Morse block, in Hz. |
| `--morse-break-duration` | `0.8` | Duration of the break tones framing the Morse block, in seconds. |

### Other

| Flag | Default | Description |
|---|---|---|
| `--spy-phonetics` | off | Use nadazero/unaone-style digit words instead of plain digits. |

### Standalone modes

These exit immediately and skip generation entirely:

| Flag | Description |
|---|---|
| `--decode GROUPS` | Decode a digit-group string and exit. |
| `--list-voices` | Print all available Kokoro voices, grouped by language, and exit. |


## default vs _nopause Scripts

The default script provides full functionality including control over the pause duration between spoken numbers.

> [!NOTE]
> the *pause* functionality is slower to run and heavier on CPU usage.

The `_nopause` script is based on an earlier version and provided for situations in which quicker/less-CPU intensive generation is required. It DOES NOT full CLI functionality as described above.
