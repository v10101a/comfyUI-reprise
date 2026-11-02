"""Stretch only Playboi's four-word shout, removing later vocals from drive and review mix."""
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'outputs/songs/playboi'
OUT = BASE / 'audio/you_see_this_shit'
RATE = 48000


def decode(path):
    return np.frombuffer(subprocess.check_output([
        'ffmpeg', '-v', 'error', '-i', str(path), '-ar', str(RATE), '-ac', '2', '-f', 'f32le', '-'
    ]), dtype=np.float32).reshape(-1, 2).copy()


def write(path, data):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes((np.clip(data, -1, 1) * 32767).astype('<i2').tobytes())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mix = decode(BASE / 'playboi_section.wav')
    vocal = decode(BASE / 'playboi_section_vocals.flac')
    # Existing songwriter-confirmed, word-aligned section boundaries (words.json).
    start, end, window, duration, pre = 21.15, 22.23, 21.0, 4.0, .25
    phrase = vocal[round(start * RATE):round(end * RATE)].copy()
    fade = round(.012 * RATE)
    phrase[:fade] *= np.linspace(0, 1, fade)[:, None]
    phrase[-fade:] *= np.linspace(1, 0, fade)[:, None]
    write(OUT / 'phrase_original.wav', phrase)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(OUT / 'phrase_original.wav'),
                    '-af', 'atempo=0.54', str(OUT / 'phrase_stretched.wav')], check=True)
    stretched = decode(OUT / 'phrase_stretched.wav')
    size = round(4.6 * RATE)
    drive = np.zeros((size, 2), dtype=np.float32)
    at = round((pre + start - window) * RATE)
    drive[at:at + len(stretched)] = stretched
    write(OUT / 'drive_preroll.wav', drive)
    lo, hi = round(window * RATE), round((window + 4.6) * RATE)
    backing = mix[lo:hi] - vocal[lo:hi]
    sung = np.zeros_like(backing)
    at_mix = round((start - window) * RATE)
    sung[at_mix:at_mix + len(stretched)] = stretched
    review = backing + sung
    peak = float(np.max(np.abs(review)))
    gain = min(1.0, .98 / max(peak, .00001))
    write(OUT / 'review_mix.wav', review * gain)
    write(OUT / 'backing.wav', backing * gain)
    report = {'originalPhraseSection': [start, end], 'phraseSpeed': .54,
              'stretchedPhraseSeconds': len(stretched) / RATE, 'clipSeconds': duration,
              'songSectionStart': window, 'drivePreroll': pre, 'followingVocalRemoved': True,
              'driveTailPeak': float(np.abs(drive[round(2.6 * RATE):]).max()), 'mixGain': gain}
    assert report['driveTailPeak'] == 0
    (OUT / 'recipe.json').write_text(json.dumps(report, indent=2))
    old = json.loads((ROOT / 'outputs/songs/jobs/jobs_pb_scream_v1.json').read_text())
    jobs = []
    for j in old[2:]:
        j.update(name=j['name'].replace('pb_scream_', 'pb_phrase_long_'),
                 audio=str((OUT / 'drive_preroll.wav').relative_to(ROOT)), start=pre, dur=duration,
                 mux_audio=str((OUT / 'review_mix.wav').relative_to(ROOT)), mux_start=0,
                 prompt="Keep the exact person in the supplied red-curtain booth frame: same face, septum and lower lip rings, platinum shag, loose striped shirt, black tie, silver headphones and flat chest. Direct-flash 35mm film texture. Sing-scream only the four words 'you see this shit', slowly and intensely in exact time with the supplied stretched vocal. Strong natural open vowels, clear consonants, focused eyes into the lens, a small head and shoulder pulse. After the final word ends, stop singing, relax the lips and hold a defiant silent stare for the remainder. No further words, no repeated phrase, no smile or laugh, no face distortion, camera locked.")
        jobs.append(j)
    target = ROOT / 'outputs/songs/jobs/jobs_pb_phrase_long.json'
    target.write_text(json.dumps(jobs, indent=2) + '\n')
    print(json.dumps(report, indent=2)); print(target)


if __name__ == '__main__':
    main()
