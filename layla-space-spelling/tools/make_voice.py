"""Record every spoken line in the game with the Kokoro neural voice.

Reads the words, planets, praise and characters straight out of index.html,
so after adding a word just run this again; only missing clips get made.

Setup (once):
    python3.12 -m venv .venv && .venv/bin/pip install kokoro-onnx soundfile phonemizer-fork
    curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
    curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

Run:
    .venv/bin/python tools/make_voice.py --model kokoro-v1.0.onnx --voices voices-v1.0.bin [--force]

Needs node and ffmpeg on PATH.
"""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

GAME = Path(__file__).resolve().parent.parent
OUT = GAME / "audio"
VOICE = "af_heart"

# Spellings that make the voice say tricky names the right way
SAY_AS = {"Makemake": "Mah-kay Mah-kay", "Haumea": "How-may-ah"}

EXTRACT_JS = r"""
const src = require('fs').readFileSync(process.argv[1], 'utf8');
const grab = (name, end) => {
  const m = src.match(new RegExp('const ' + name + ' = ([\\s\\S]*?' + end + ');'));
  return new Function('return ' + m[1])();
};
console.log(JSON.stringify({
  words: grab('WORDS', '\\n}'), bodies: grab('BODIES', '\\n}'), heroes: grab('HEROES', '\\n}'),
  praise: grab('PRAISE', '\\]'), journey: grab('JOURNEY', '\\]')
}));
"""


def game_lines():
    data = json.loads(subprocess.check_output(["node", "-e", EXTRACT_JS, str(GAME / "index.html")]))
    lines = {}  # clip id -> (text, speed)
    for tier in data["words"].values():
        for word, _emoji in tier:
            lines[f"word_{word}"] = (word, 0.85)
            lines[f"type_{word}"] = (f"Can you type... {word}?", 0.9)
    for key in data["journey"][1:]:
        b = data["bodies"][key]
        lines[f"next_{key}"] = (f"Next stop, {b['name']}!", 0.95)
        if key != data["journey"][-1]:
            lines[f"welcome_{key}"] = (f"Welcome to {b['name']}! {b['fact']}", 0.92)
    for i, p in enumerate(data["praise"]):
        lines[f"praise_{i}"] = (p, 0.95)
    # A bare letter comes out with a trailing "-ah" (T -> "tee-ah"), so say it inside a sentence
    for c in "abcdefghijklmnopqrstuvwxyz":
        lines[f"letter_{c}"] = (f"Look for the {c.upper()} key!", 0.9)
    mm = data["bodies"]["makemake"]["fact"]
    for key, h in data["heroes"].items():
        lines[f"hi_{key}"] = (f"Hi! I'm {h['name']}!", 0.95)
        lines[f"win_{key}"] = (f"Hooray! {h['name']} made it all the way to Makemake! {mm} You are a super typer!", 0.92)
    return lines


def kokoro(model, voices):
    import espeakng_loader
    from kokoro_onnx import EspeakConfig, Kokoro

    # espeak-ng chokes on long data paths (fixed 160-char buffer), so point it at a short symlink
    short = Path(os.environ.get("ESPEAK_SHORT_DIR", "/tmp/espeak-ng-data"))
    if not short.exists():
        short.symlink_to(espeakng_loader.get_data_path())
    os.environ["ESPEAK_DATA_PATH"] = str(short)
    cfg = EspeakConfig(lib_path=espeakng_loader.get_library_path(), data_path=str(short))
    return Kokoro(model, voices, espeak_config=cfg)


def letter_phonemes(tts, c):
    # In a sentence espeak reads "A" as the article "uh", so splice in the letter's own name
    name = tts.tokenizer.phonemize(c.upper(), "en-us").strip()
    the = "ðɪ" if c in "aefhilmnorsx" else "ðə"
    return f"lˈʊk fɚ{the} {name} kˈiː!"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--voices", required=True)
    ap.add_argument("--force", action="store_true", help="re-record clips that already exist")
    args = ap.parse_args()

    import soundfile as sf

    OUT.mkdir(exist_ok=True)
    todo = {k: v for k, v in game_lines().items() if args.force or not (OUT / f"{k}.mp3").exists()}
    print(f"{len(todo)} clips to record")
    if not todo:
        return
    tts = kokoro(args.model, args.voices)
    with tempfile.TemporaryDirectory() as tmp:
        for n, (cid, (text, speed)) in enumerate(sorted(todo.items()), 1):
            for name, spoken in SAY_AS.items():
                text = text.replace(name, spoken)
            if cid.startswith("letter_"):
                samples, rate = tts.create(letter_phonemes(tts, cid[-1]), voice=VOICE, speed=speed, is_phonemes=True)
            else:
                samples, rate = tts.create(text, voice=VOICE, speed=speed, lang="en-us")
            wav = Path(tmp) / f"{cid}.wav"
            sf.write(wav, samples, rate)
            subprocess.run(
                ["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav),
                 "-af", "silenceremove=start_periods=1:start_threshold=-50dB,apad=pad_dur=0.05",
                 "-ac", "1", "-b:a", "64k", str(OUT / f"{cid}.mp3")],
                check=True,
            )
            print(f"[{n}/{len(todo)}] {cid}: {text}")


if __name__ == "__main__":
    main()
