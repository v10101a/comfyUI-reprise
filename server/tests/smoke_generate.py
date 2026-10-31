"""Real in-world API integration against an analyzed project. Usage: smoke_generate.py <project-id>."""
import json
import sys
import time
import httpx

pid = sys.argv[1]
with httpx.Client(base_url="http://127.0.0.1:8787", timeout=60) as client:
    project = client.get(f"/api/projects/{pid}").raise_for_status().json()
    job = client.post(f"/api/projects/{pid}/generate/inworld", json={"wordIds": [project["words"][0]["id"]], "prompt": "Large luminous neon lettering, gentle camera push, keep letters readable", "start": 0, "end": min(1, project["duration"])}).raise_for_status().json()
    for _ in range(900):
        job = client.get(f"/api/jobs/{job['id']}").raise_for_status().json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(1)
    print(json.dumps(job, indent=2), flush=True)
    assert job["status"] == "done", job
    project = client.get(f"/api/projects/{pid}").raise_for_status().json()
    shot = next(s for s in project["shots"] if s["id"] == job["result"]["shotId"])
    assert shot["status"] == "done" and shot["plate"] and shot["video"], shot
    assert project["words"][0]["shotId"] == shot["id"]
    response = client.get(f"/files/projects/{pid}/{shot['video']}").raise_for_status()
    assert len(response.content) > 1000
    print("PASS: plate → LTX → shot attachment → downloadable video")
