"""Prepared vocal staging and output timing, without ComfyUI/network access."""
import os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

TMP=tempfile.TemporaryDirectory();os.environ.setdefault('TYPESET_DATA_DIR',TMP.name)
from app import workflows
from app.store import ProjectStore
from app.media import ffmpeg,probe_media,make_test_video

class VocalRecipeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=ProjectStore(Path(self.tmp.name)/'projects');self.p=self.store.create('Vocal test');self.root=self.store.project_dir(self.p.id)
        (self.root/'audio').mkdir();self.audio=self.root/'audio/drive.wav'
        ffmpeg(['-f','lavfi','-i','sine=frequency=330:sample_rate=48000:duration=2.5',self.audio])
        self.p.media.audio=probe_media(self.audio,'audio/drive.wav');self.p.media.audioClip={'in':1,'out':2,'offset':0};self.store.save(self.p)
        self.service=SimpleNamespace(store=self.store,require_project=self.store.load)
        self.meta={'target':'local','inputs':{'audio':{'role':'media','media':'audio'}},'output':{'node':'15','type':'video'},'missing':[],'missingModels':[]}

    def test_prepared_file_stays_in_its_own_time_while_song_uses_audio_clip(self):
        stage=Mock(return_value='staged.wav');work=self.root/'cache';work.mkdir()
        _,prov=workflows._stage_media(self.store,self.p,{'media':'audio'},{'path':'audio/drive.wav','start':0,'end':2.5},work,stage)
        self.assertEqual(prov['songStart'],0);self.assertEqual(prov['path'],'audio/drive.wav')
        self.assertAlmostEqual(probe_media(stage.call_args.args[0],'').duration,2.5,places=2)
        _,song=workflows._stage_media(self.store,self.p,{'media':'audio'},{'start':.2,'end':.7},work,stage)
        self.assertEqual(song['songStart'],1.2)

    def test_preflight_rejects_missing_outside_files_and_invalid_retime_before_queue(self):
        with patch.object(workflows,'get_workflow',return_value=self.meta):
            for source in ('audio/nope.wav','../../outside.wav','/etc/passwd'):
                with self.subTest(source=source),self.assertRaises(workflows.WorkflowApiError):
                    workflows.check_run(self.service,self.p.id,'wf',{'sources':{'audio':{'path':source}}})
            for pp in ({'timeScale':0,'trimStart':.25,'fps':24},{'timeScale':.8,'trimStart':float('nan'),'fps':24}):
                with self.assertRaises(workflows.WorkflowApiError):workflows.check_run(self.service,self.p.id,'wf',{'postprocess':pp})
            workflows.check_run(self.service,self.p.id,'wf',{'sources':{'audio':{'path':'audio/drive.wav'}},'postprocess':{'timeScale':.8,'trimStart':.25,'fps':24,'audio':'audio/drive.wav'}})

    def test_returned_video_has_original_timing_24fps_and_original_audio(self):
        raw=make_test_video(self.root/'raw.mp4',duration=2.5,fps=16,size='80x48')
        out=workflows._retime_output(self.store,self.p.id,raw,self.root,{'timeScale':.8,'trimStart':.25,'fps':24,'audio':'audio/drive.wav'})
        ref=probe_media(out,'result.mp4');self.assertEqual(ref.fps,24);self.assertTrue(ref.hasAudio)
        # Same interpolation/trim as the CLI; interpolation needs an adjacent frame at its tail.
        self.assertGreater(ref.duration,1.5);self.assertLess(ref.duration,1.9)

if __name__=='__main__':unittest.main()
