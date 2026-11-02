"""Head tracks cache by source, merge safely with edits, and never require a matte or GPU."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from app.head_tracking import analyze_heads, head_sources, choose_face, track_source
from app.models import Project
from app.store import ProjectStore


class Context:
    def progress(self, *args): pass


class HeadTrackingTests(unittest.TestCase):
    def test_sources_skip_bin_only_and_hidden_assets_but_deduplicate_split_clips(self):
        p = Project(id='test', name='test', assets=[dict(id='a',path='a.mp4',kind='video'),dict(id='b',path='b.mp4',kind='video')],
                    layers=[dict(kind='media',assetId='a'),dict(kind='media',assetId='a'),dict(kind='media',assetId='b',hidden=True)])
        self.assertEqual(head_sources(p), [dict(path='a.mp4',kind='video')])
        self.assertEqual(head_sources(Project(id='empty',name='empty')), [])

    def test_face_continuity_prefers_main_subject_over_a_small_bystander(self):
        a = np.array([100,50,50,70]+[0]*10+[.9], dtype=float)
        b = np.array([200,60,20,20]+[0]*10+[.99], dtype=float)
        self.assertTrue(np.array_equal(choose_face(np.array([b,a]),a),a))
        self.assertIsNone(choose_face(None,a))

    def test_actual_cpu_model_reports_no_face_on_blank_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'empty.png';Image.new('RGB',(320,180),'black').save(path)
            doc=track_source(path,'image')
            self.assertEqual((doc['width'],doc['height']), (320,180))
            self.assertEqual(doc['tracks'][0]['frames'], [])

    def test_job_merges_only_analysis_and_cache_survives_trim_or_text_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=ProjectStore(Path(tmp));p=store.create('Heads')
            path=store.project_dir(p.id)/'media/test.png';path.parent.mkdir(exist_ok=True);Image.new('RGB',(40,40)).save(path)
            def setup(q):
                q.assets=[dict(id='a',kind='image',path='media/test.png')]
                q.layers=[dict(id='clip',kind='media',assetId='a',start=1,**{'in':0},out=2)]
                q.analysis.matte='analysis/matte/'
            store.update(p.id,setup)
            doc=dict(fps=12,frames=1,width=40,height=40,tracks=[dict(id='person0',label='head',frames=[])])
            def detect(*args):
                def concurrent(q):
                    q.name='Edited while tracking';q.layers[0]['start']=3
                store.update(p.id,concurrent)
                return doc
            with patch('app.head_tracking.track_source',side_effect=detect) as mock:
                result=analyze_heads(store,p.id,Context());analyze_heads(store,p.id,Context())
                self.assertEqual(mock.call_count,1)
            q=store.load(p.id)
            self.assertEqual(q.name,'Edited while tracking');self.assertEqual(q.layers[0]['start'],3)
            self.assertEqual(q.analysis.matte,'analysis/matte/')
            self.assertEqual(q.analysis.headTracks,result['headTracks'])
            self.assertEqual(json.loads((store.project_dir(p.id)/q.analysis.headTracks['media/test.png']).read_text()),doc)


if __name__=='__main__':unittest.main()
