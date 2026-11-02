"""Scene generation provenance survives completion without requiring a timeline layer."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

TMP=tempfile.TemporaryDirectory()
os.environ.setdefault('TYPESET_DATA_DIR',TMP.name)
from app import workflows
from app.models import Project
from app.store import ProjectStore

class SceneWorkflowTests(unittest.TestCase):
    def test_scene_outputs_keep_origin_without_placing_a_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'result.png';raw.write_bytes(b'test-output')
            added=[]
            def add(pid,name,data,source,place,label):
                a={'id':f'a{len(added)}','kind':'image','path':'result.png','source':source};added.append((a,place));return a
            service=SimpleNamespace(store=SimpleNamespace(project_dir=lambda _:root),require_project=lambda _:SimpleNamespace(fps=24),add_asset=add)
            runner=Mock();runner.run.return_value=SimpleNamespace(outputs={'result':[str(raw)]},job_id='comfy-prompt',timing={})
            meta={'target':'local','inputs':{},'name':'Scene motion'}
            with patch.object(workflows,'check_run',return_value=meta),patch.object(workflows,'runner',runner),patch.object(workflows,'_single_file',return_value=raw),patch.object(workflows,'_dir',return_value=root):
                result=workflows.run_workflow(service,'project','workflow',{'sceneId':'wind-scene','variants':2},Mock())
            self.assertEqual(len(result['assets']),2)
            for a,place in added:
                self.assertEqual(a['source']['sceneId'],'wind-scene');self.assertNotIn('layerId',a['source']);self.assertFalse(place)

    def test_scene_recipe_and_old_board_round_trip_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=ProjectStore(Path(tmp));p=store.create('Scene')
            value=p.model_dump();value['board']={'cards':[{'id':'old','kind':'note','text':'Keep me'}], 'scenes':[{'id':'scene','name':'Wind','clips':[],'takes':[],'refs':['face'],'x':-400,'y':60,'generation':{'workflowId':'wf','workflows':{'wf':{'sources':{'image':'face'},'inputs':{'prompt':'wind'}}}}}]}
            store.save(Project.model_validate(value));loaded=store.load(p.id).model_dump()
            self.assertEqual(loaded['board'],value['board'])

if __name__=='__main__':unittest.main()
