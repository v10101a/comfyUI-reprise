"""CPU behavioral tests, independent of a running ComfyUI/model download."""
import importlib.util
import json
from pathlib import Path
import unittest
import torch
ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/f'{name}.py')
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
words=module('whisper_words')
tracks=module('tracks')
text=module('text_mask')

class NodeTests(unittest.TestCase):
    def test_empty_recognition_does_not_invent_lyrics(self):
        result=words.build_words_json([],[], 'en','small','The unheard words')
        self.assertEqual(result['words'],[])
        self.assertEqual(result['source'],'faster-whisper')

    def test_lyric_correction_and_insertions_remain_ordered(self):
        rec=[dict(text='Neon',start=.2,end=.5,confidence=.9,seg=0),dict(text='lights',start=1,end=1.4,confidence=.8,seg=0)]
        out, lines=words.align_to_lyrics(rec,'Neon bright\nlights')
        self.assertEqual([w['text'] for w in out],['Neon','bright','lights'])
        self.assertEqual(out[1]['confidence'],0)
        self.assertTrue(all(w['end']>w['start'] for w in out))
        self.assertTrue(all(a['end']<=b['start'] for a,b in zip(out,out[1:])))
        self.assertEqual([x['id'] for x in lines],['l0','l1'])

    def test_song_section_tags_are_not_lyrics(self):
        rec=[dict(text=t,start=i*.5,end=i*.5+.4,confidence=.9,seg=0) for i,t in enumerate('Hold on say the soul'.split())]
        out, lines=words.align_to_lyrics(rec,'[chorus]\nHold on, say it slow\n\n(x2)')
        self.assertEqual([w['text'] for w in out],['Hold','on,','say','it','slow'])
        self.assertEqual([x['text'] for x in lines],['Hold on, say it slow'])

    def test_masks_preserve_missing_frames_and_largest_component(self):
        mask=torch.zeros(3,100,100)
        mask[0,10:50,20:60]=1
        mask[0,80:85,80:85]=1
        mask[2,10:50,60:100]=1
        raw,count=tracks.MaskToTracks().run(24,'person',mask=mask,smooth=3)
        data=json.loads(raw); fr=data['tracks'][0]['frames']
        self.assertEqual(count,2)
        self.assertEqual([x['f'] for x in fr],[0,2])
        self.assertEqual(fr[0]['bbox'],[.2,.1,.4,.4])
        self.assertAlmostEqual(fr[0]['cx'],.4)
        self.assertAlmostEqual(fr[1]['cx'],.8) # smoothing must not bridge absent frame

    def test_text_mask_is_nonempty_at_requested_size(self):
        mask,image=text.TextToMask().run('NEON','Anton',.2,.5,.5,512,320)
        self.assertEqual(tuple(mask.shape),(1,320,512))
        self.assertEqual(tuple(image.shape),(1,320,512,3))
        self.assertGreater(mask.sum().item(),100)
        self.assertEqual(mask.max().item(),1)
        self.assertEqual(mask.min().item(),0)

if __name__=='__main__':unittest.main()
