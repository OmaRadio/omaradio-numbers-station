# OmaRadio TX Numbers Station

OmaRadio sometimes operates as a numbers station to send out clandestine messages to Omarchy operatives worldwide. The scripts here can generate the broadcast audio including an "Announcement" message & "Message File" which gets transformed to encoded number form. The supplied written text is passed through Kokoro TTS.

## Dependencies

**Mandatory:**  
Python packages `kokoro-onnx, soundfile, numpy`

The Kokoro model weights are a SEPARATE one-time download. Run once, in the same directory as this script (or pass
--model / --voices to point elsewhere):

```
    wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
    wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```

If the above 404 error, check the repo for a new release.

The script should install the python package dependencies via `uv` on first run if not already installed.
Optional Manual `uv` install, if you'd rather keep a persistent environment: 
`uv venv && uv pip install kokoro-onnx soundfile numpy`

OR, inside a `uv`-managed project:  
`uv add kokoro-onnx soundfile numpy`

Optional (Recommended and required for audio output):  
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
`uv run omaradio_numbers_station_pause.py --audio --format mp3 --degrade heavy --voice bm_daniel --message-speed 0.93 --digit-pause 0.20`

Simple usage with defaults

```
    uv run omaradio_numbers_station_pause.py --audio
    uv run omaradio_numbers_station_pause.py --audio --format mp3
```

The script can also be called via `python` with using `uv` (Direct):  
```
Usage:
    python3 omaradio_numbers_station_pause.py                               # cipher only, no audio
    python3 omaradio_numbers_station_pause.py --audio                       # render .wav, "classic" radio effect
    python3 omaradio_numbers_station_pause.py --audio --degrade none        # clean, undegraded take
    python3 omaradio_numbers_station_pause.py --audio --degrade heavy       # barely-legible static mess
    python3 omaradio_numbers_station_pause.py --audio --format mp3          # render .mp3 instead
    python3 omaradio_numbers_station_pause.py --audio --format both         # render both
    python3 omaradio_numbers_station_pause.py --audio --voice bm_george     # different Kokoro voice
    python3 omaradio_numbers_station_pause.py --list-voices                 # show all available voices
    python3 omaradio_numbers_station_pause.py --decode "00 19 12"           # decode a group string and exit
    python3 omaradio_numbers_station_pause.py --spy-phonetics --audio       # NATO-telephony digit words
```


## _pause vs _nopause Scripts

The `_pause` script provides the functionality for controlling the pause duration between spoken numbers.

> [!NOTE]
> the `_pause` script is preferred for use as it is the latest version and supports passing in message files.
> **HOWEVER** It is slower to run and heavier on CPU.

The `_nopause` script is based on an earlier version and provided for situations in which quicker/less-CPU intensive generation is required.
