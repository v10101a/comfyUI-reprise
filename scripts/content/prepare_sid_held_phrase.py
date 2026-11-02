"""One continuous extended 'no place to hide away' vocal for a standalone take."""
import json
import shutil
import subprocess
from pathlib import Path
import numpy as np
from prepare_pb_phrase import decode, write, RATE

BASE=Path('outputs/songs/so-i-die')
OUT=BASE/'audio/no_place_held'
OUT.mkdir(parents=True,exist_ok=True)
lead=decode(BASE/'audio/drive/sid_hold_22p25.wav')
origin=22.25
def section(a,b): return lead[round((a-origin)*RATE):round((b-origin)*RATE)].copy()
head,hold,tail=section(23.333,24.6),section(24.6,26.6),section(26.6,26.934)
write(OUT/'vowel_original.wav',hold)
subprocess.run(['ffmpeg','-v','error','-y','-i',str(OUT/'vowel_original.wav'),'-af','atempo=0.5',str(OUT/'vowel_extended.wav')],check=True)
held=decode(OUT/'vowel_extended.wav')
def join(a,b,n=720):
    ramp=np.linspace(0,1,n)[:,None]
    return np.concatenate([a[:-n],a[-n:]*(1-ramp)+b[:n]*ramp,b[n:]])
phrase=join(join(head,held),tail)
fade=round(.012*RATE)
phrase[:fade]*=np.linspace(0,1,fade)[:,None]
phrase[-round(.08*RATE):]*=np.linspace(1,0,round(.08*RATE))[:,None]
write(OUT/'phrase.wav',phrase)
duration,preroll,lead_in=6.5,.25,.15
voice=np.zeros((round(duration*RATE),2),np.float32)
at=round(lead_in*RATE);voice[at:at+len(phrase)]=phrase
write(OUT/'vocal.wav',voice)
drive=np.concatenate([np.zeros((round(preroll*RATE),2),np.float32),voice])
write(OUT/'drive_preroll.wav',drive)
subprocess.run(['ffmpeg','-v','error','-y','-i',str(OUT/'drive_preroll.wav'),'-af','atempo=0.8',str(OUT/'drive.wav')],check=True)
mix=decode(BASE/'so-i-die_section.wav'); vocals=decode(BASE/'so-i-die_section_vocals.flac')
window=23.333-lead_in;lo=round(window*RATE);hi=lo+len(voice)
backing=mix[lo:hi]-vocals[lo:hi]
review=backing+voice
gain=min(1,.98/max(float(np.abs(review).max()),.00001))
write(OUT/'backing.wav',backing*gain);write(OUT/'song.wav',review*gain)
assert not np.any(voice[at+len(phrase):])
report=dict(sourcePhrase=[23.333,26.934],heldVowelSource=[24.6,26.6],vowelSpeed=.5,
            phraseSeconds=len(phrase)/RATE,clipSeconds=duration,vocalStart=lead_in,
            followingLyricIncluded=False,drivePreroll=preroll,driveSpeed=.8,mixGain=gain)
(OUT/'recipe.json').write_text(json.dumps(report,indent=2))
pid='48f2389d-1d2e-42ff-af86-f90b4d8c4600'
dest=Path('data/projects')/pid/'audio/no_place_held';dest.mkdir(parents=True,exist_ok=True)
for name in ('drive.wav','song.wav'): shutil.copy2(OUT/name,dest/name)
p=json.loads((Path('data/projects')/pid/'project.json').read_text())
draft=next(l['generation']['workflows']['ed3fbc575706'] for l in p['layers'] if l['id']=='so-i-die-shot-07')
draft['inputs'].update(seed=307,length=137,width=832,height=480,prompt="One continuous close performance on the subway platform. The same person softly sings the supplied words 'no place to hide away', then sustains the long final vowel without interruption. Quietly dramatic and vulnerable: they breathe in, their gaze falls away, eyes slowly close, chin lifts just a little as the long note grows, shoulders settle. Natural relaxed lips and jaw, small effortless mouth shapes, no toothy grin, no forced wide-open mouth. Keep singing the same smooth held vowel throughout the sustained vocal; do not restart the line or mouth another lyric. At the end let the lips relax and breathe. A tunnel draft moves the short hair and coat collar. Camera makes a slow gentle physical push closer during the long note, uninterrupted real-time shot. Exact same real face, septum and lip rings, short silver-blue dark-underneath hair, black leather coat, small flat chest. Grainy 35mm film, natural skin and subway fluorescent light.")
draft['mediaFiles']={'audio':{'path':'audio/no_place_held/drive.wav','name':'No place to hide away · extended held vowel'}}
draft['postprocess']={'timeScale':.8,'trimStart':.25,'fps':24,'audio':'audio/no_place_held/song.wav'}
cfg=dict(name='sid_no_place_held',title='No place to hide away · continuous long hold',project=pid,layer='so-i-die-shot-07',workflow='ed3fbc575706',draft=draft,
         boardGroup={'id':'sid-long-held-phrase','title':'So I Die · one continuous held phrase'},boardIndex=0)
folder=BASE/'reviews/held_phrase';folder.mkdir(parents=True,exist_ok=True)
(folder/'sid_no_place_held.json').write_text(json.dumps(cfg,indent=2))
print(json.dumps(report))
