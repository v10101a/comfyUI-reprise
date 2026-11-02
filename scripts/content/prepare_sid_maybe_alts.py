"""Prepare two phrase-only alternatives from the liked escalator recipes."""
import copy
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from prepare_pb_phrase import decode, write, RATE

BASE = Path('outputs/songs/so-i-die')
OUT = BASE / 'audio/maybe_myself_alts'
REVIEW = BASE / 'reviews/maybe_myself_alts'
OUT.mkdir(parents=True, exist_ok=True)
REVIEW.mkdir(parents=True, exist_ok=True)
window, start, end, duration, pre = 11.1, 11.346, 13.02, 2.6, .25
mix = decode(BASE / 'so-i-die_section.wav')
vocal = decode(BASE / 'so-i-die_section_vocals.flac')
lo, size = round(window * RATE), round(duration * RATE)
voice = np.zeros((size, 2), dtype=np.float32)
phrase = vocal[round(start * RATE):round(end * RATE)].copy()
fade = round(.01 * RATE)
phrase[:fade] *= np.linspace(0, 1, fade)[:, None]
phrase[-fade:] *= np.linspace(1, 0, fade)[:, None]
at = round((start-window) * RATE)
voice[at:at+len(phrase)] = phrase
backing = mix[lo:lo+size] - vocal[lo:lo+size]
review = backing + voice
gain = min(1., .98/max(float(np.abs(review).max()), .00001))
write(OUT/'vocal.wav', voice)
write(OUT/'song.wav', review*gain)
write(OUT/'drive_preroll.wav', np.concatenate([np.zeros((round(pre*RATE), 2), dtype=np.float32), voice]))
subprocess.run(['ffmpeg','-v','error','-y','-i',str(OUT/'drive_preroll.wav'),
                '-af','atempo=0.8,apad,atrim=duration=3.5625',str(OUT/'drive.wav')],check=True)
assert not np.any(voice[at+len(phrase):])
recipe = dict(sourcePhrase=[start,end],songSectionStart=window,phraseSpeed=1,
              clipSeconds=duration,drivePreroll=pre,driveSpeed=.8,
              precedingVocalRemoved=True,followingLyricIncluded=False,mixGain=gain)
(OUT/'recipe.json').write_text(json.dumps(recipe,indent=2))
pid = '48f2389d-1d2e-42ff-af86-f90b4d8c4600'
dest = Path('data/projects')/pid/'audio/maybe_myself_alts'
dest.mkdir(parents=True,exist_ok=True)
for name in ('drive.wav','song.wav'): shutil.copy2(OUT/name,dest/name)
variants = [
    ('approved_escalator/sid_up_approved_maybe.json', 'sid_maybe_myself_up_alt',
     'Maybe…myself · upward / wry glance', 29, 'a_1ec22d3840',
     'A small wry look of self-recognition: the eyes dip briefly on the middle of the line, then return softly toward the camera on the final word. No laugh or broad smile, just a hint of feeling in the eyes.'),
    ('fresh_escalators/sid_esc_parallel_fringe_maybe.json', 'sid_maybe_myself_parallel_alt',
     'Maybe…myself · parallel / passing glance', 43, 'a_110b6f8202',
     'A reflective passing glance: the head turns just a few degrees toward the camera during the line, then the gaze settles just past the lens. Keep the slight turn easy and unforced.'),
]
for source,name,title,seed,parent,direction in variants:
    cfg = copy.deepcopy(json.loads((BASE/'reviews'/source).read_text()))
    cfg.update(name=name,title=title,scene='g-group-so-i-die-shot-02',parentAsset=parent,
               phrase={'text':'Maybe…laugh at myself','sourceStart':start,'sourceEnd':end,'onlyThisPhrase':True})
    for key in ('boardGroup','boardIndex','conditioning'): cfg.pop(key,None)
    inputs = cfg['draft']['inputs']
    inputs.update(seed=seed,length=57)
    inputs['prompt'] = inputs['prompt'].replace('with rising intensity, brows a little drawn,','quietly, with relaxed brows,')
    inputs['prompt'] += ' '+direction+' Sing only the supplied short phrase, using small natural mouth shapes. After the final word, let the lips close and hold the expression while the escalator keeps moving. No following lyric, no repeated words, no extra mouth movements or exaggerated jaw.'
    cfg['draft']['mediaFiles']={'audio':{'path':'audio/maybe_myself_alts/drive.wav','name':'Maybe…myself · phrase only','duration':3.5625}}
    cfg['draft']['postprocess']={'timeScale':.8,'trimStart':.25,'fps':24,'audio':'audio/maybe_myself_alts/song.wav'}
    cfg['reviewNote']='Alternative of the liked parent take, same face and moving scene; only the requested lyric, with a short silent-vocal hold. User review pending.'
    (REVIEW/(name+'.json')).write_text(json.dumps(cfg,indent=2))
print(json.dumps(recipe))
