# Connect to ComfyUI over Tailscale

Tailscale provides a private network connection. ComfyUI runs on the computer
with the GPU; this project sends workflows and downloads their results. That
computer must be awake and ComfyUI must be running for jobs to work.

## Current GPU host

Use **http://100.104.17.103:8188** directly over Tailscale. The RTX 4090 host is reachable, VideoHelperSuite loaded after its restart, and both Krea2 image generation and a short MiniMax H3 image-to-video render have succeeded using existing weights. No SSH tunnel or additional download is needed for those workflows.

From this checkout, `server/.venv/bin/python scripts/render_available.py` runs Krea on the GPU host and LTX on the Mac. Add `--video-model minimax` to run both image and video generation on the GPU host. Outputs download to `outputs/available-models/<run>/`. See [measurements and limitations](model-eval.md).

Add `--full-size` with MiniMax for the verified 1344×768, 124-frame render (about five seconds). The short default is 736×416 and 56 frames. A full-size example is already imported into the local editor as **Typeset — GPU neon demo**.

The app's optional remote SDK transport is implemented separately: [server setup](server.md#remote-comfyui). Keep its LTX jobs local until the remote T5 encoder is available. The remote host has only about 3.6 GB free, so [additional weight downloads are deferred](gpu-host-install.md).

## Earlier connection attempt: a different Mac

The instructions below document the earlier `100.73.225.117` connection. They are an alternative for a host that needs SSH forwarding, not prerequisites for the current 4090 setup.

On October 30, 2026, `100.73.225.117` appeared in Tailscale as
`steyr.tailc53f5.ts.net`, “Aaron’s MacBook Pro,” running macOS. SSH on port 22
accepted a connection and returned an OpenSSH banner. ComfyUI on port 8188
returned **connection refused**. The proxy on 8189 and web ports 80/443 were
also unreachable. No SSH login or remote workflow has been completed.

This establishes network reachability to SSH, not whether ComfyUI is installed
or running on localhost. It could also be using a different port. Confirm with
Aaron that this is the intended compute machine and get the account you may
use for SSH. A machine share does not grant an operating-system login or access
to other GPU machines in his network.

## Recommended first connection: SSH tunnel

SSH is already reachable. Once Aaron supplies a working login, its port
forwarding lets your browser reach a service listening only on his computer's
localhost. It does not install or start ComfyUI. This uses normal OpenSSH over
Tailscale; it does not require enabling the separate Tailscale SSH feature.

### On Aaron's computer

First open his existing ComfyUI installation and check its actual port. For a
manual installation with a virtual environment named `.venv`, start it from its
installation folder (use his real path):

```bash
cd /actual/path/to/ComfyUI
.venv/bin/python main.py --listen 127.0.0.1 --port 8188
```

Leave that terminal running. In another terminal **on Aaron's computer**, check:

```bash
curl --fail http://127.0.0.1:8188/system_stats
```

A JSON response confirms the server and reports its compute devices. If he uses
Comfy Desktop, start its instance through the app and use the port it shows;
do not assume its installation path or launch a duplicate instance. If no
installation exists, follow the [official manual installation guide](https://docs.comfy.org/installation/manual_install)
for his hardware, or [Comfy Desktop for an Apple Silicon Mac](https://docs.comfy.org/installation/desktop/macos).

For this repository's SDK runner, also start the API proxy in that ComfyUI
environment. These commands assume the same manual `.venv` installation:

```bash
cd /actual/path/to/ComfyUI
.venv/bin/python -m pip install comfy-api-proxy
.venv/bin/comfy-api-proxy run \
  --comfyui http://127.0.0.1:8188 \
  --host 127.0.0.1 --port 8189 \
  --comfyui-base-dir "$PWD"
```

Leave it running and check `http://127.0.0.1:8189/api/v2/health` on his computer.
The browser UI needs only ComfyUI; the SDK runner also needs this proxy.

### On your Mac, from this repository

Replace `ACCOUNT` with the account Aaron authorizes, not his email address:

```bash
bash scripts/comfy-remote.sh connect ACCOUNT@100.73.225.117
```

Use the SSH authentication method Aaron sets up. Enter passwords only in the
SSH prompt. On the first connection, confirm the host key fingerprint with him.
The helper retains normal SSH host-key checking. Leave the terminal open.

In a second terminal:

```bash
bash scripts/comfy-remote.sh status
```

When ComfyUI's check returns HTTP 200, open **http://127.0.0.1:18188** in your
browser. That address reaches Aaron's ComfyUI through the tunnel. Your existing
local ComfyUI stays on 8188. Ctrl-C in the tunnel terminal closes the connection.
The helper assumes remote ports 8188/8189; adapt its SSH forwards if Aaron uses
different ports.

### Verify workflow submission and download

After both checks succeed, run in the second terminal:

```bash
export COMFY_BASE_URL=http://127.0.0.1:18189
~/ComfyUI/.venv/bin/python scripts/run_local_workflow.py \
  docs/workflows/remote_smoke_api.json 2 --out outputs/remote-smoke
```

This submits a tiny solid-color image workflow on his machine and downloads its
PNG here. It requires no checkpoint or uploaded input. It verifies execution and
download, not GPU inference performance. If his proxy requires a token, set
`COMFY_API_KEY` locally before running. Then test the existing LTX workflow once
its models and VideoHelperSuite are installed on his machine.

## Alternative: Aaron publishes ComfyUI with Tailscale Serve

If Aaron prefers to give you browser/API access without an SSH account, he can
publish his running localhost service to permitted Tailscale peers. Run these
**on his computer**, after the localhost checks pass:

```bash
tailscale serve --bg --tcp=8188 tcp://127.0.0.1:8188
tailscale serve --bg --tcp=8189 tcp://127.0.0.1:8189
tailscale serve status
```

If the macOS `tailscale` command is not in PATH, use
`/Applications/Tailscale.app/Contents/MacOS/Tailscale` instead. If Serve displays
an enablement URL, Aaron follows it for his tailnet. Access policies must allow
your shared-user connection to the selected ports. Serve exposes the service
privately over Tailscale. Use Serve, rather than the public-internet Funnel feature.

With these ports configured, open `http://100.73.225.117:8188` and set
`COMFY_BASE_URL=http://100.73.225.117:8189` for the SDK runner. Aaron can remove
just these forwards with `tailscale serve --tcp=8188 off` and
`tailscale serve --tcp=8189 off`.

## Troubleshooting

| Symptom | Next check |
|---|---|
| SSH says permission denied | Ask Aaron for the authorized OS account and authentication setup. Tailscale access alone is insufficient. |
| SSH says address already in use | A local tunnel port is occupied. Inspect the existing tunnel/service before starting another. |
| Tunnel is open but status fails | Check ComfyUI/proxy on Aaron's localhost and confirm their actual ports. SSH can start a tunnel before those services are running. |
| Browser works but SDK does not | Check the proxy on remote port 8189 and any token it requires. |
| Missing model or custom node | Install it on the compute machine; the copies on this Mac are not available remotely. |

## App integration and the older tunnel helper

The backend now has an explicit remote LTX runner with remote input uploads,
remote output downloads, and a separate SDK proxy. Analysis and plate generation
stay local. This mode avoids local filesystem shortcuts even when a remote host
is reached through a localhost tunnel. See [enable and rollback commands](server.md#remote-comfyui).

The helper's `env` command prints the three existing URL variables for reference;
it does not apply the app's newer remote settings. The evaluation script omits
Mac memory measurements for a remote IP; a localhost tunnel still looks local to
that script, so its Mac memory figures are not remote GPU measurements.

## References

- [Tailscale machine sharing and access policies](https://tailscale.com/docs/features/sharing)
- [OpenSSH local port forwarding (`-L`) and authentication](https://man.openbsd.org/ssh)
- [Tailscale Serve TCP forwarding and macOS support](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [ComfyUI API proxy setup](https://docs.comfy.org/development/comfyui-server/api-proxy)
