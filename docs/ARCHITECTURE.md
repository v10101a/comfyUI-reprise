# Typeset — architecture

Typeset is a local typography editor: transcribe words, correct their timing, place them over or behind subjects or relative to mask-derived anchors, and export a finished clip or transparent text layer. LTX adds optional short animated lettering shots. The implementation is an early prototype; the node-based ComfyUI editor remains available independently.

## Components

| Path | Responsibility |
|---|---|
| `apps/web/` | React/Vite editor, offline synthetic sample, waveform/timeline, inspector, deterministic Canvas renderer and `#/render` route |
| `server/` | FastAPI projects/uploads/jobs, Comfy SDK sidecar runner, Chromium frame capture and ffmpeg exports |
| `workflows/` | Production API graphs plus input/output sidecars |
| `custom_nodes_dev/typeset_nodes/` | Whisper timings, text JSON output, mask-derived anchors, font masks and prototype lettering plate |
| `workflows/eval/`, `scripts/eval/`, `docs/model-eval.md` | Separate model quality experiments and recorded results |

Shared formats are defined in [SCHEMA.md](SCHEMA.md). Operational details and checks live in [web.md](web.md), [server.md](server.md), and [comfy-integration.md](comfy-integration.md).

## Runtime

```text
browser / Vite → FastAPI :8787 → Comfy SDK → local proxy :8189 → ComfyUI :8188
                       ↓
                Playwright Chromium → web #/render → PNG frames → ffmpeg
```

ComfyUI lives outside this checkout at `~/ComfyUI`, with MPS inference on the development Mac. Model files live there as well. The web port defaults to 5173; `scripts/dev.sh` chooses the next free port through 5180. **This session uses 5174 because another app owns 5173.** `TYPESET_WEB_URL` and `TYPESET_CORS_ORIGINS` must match the selected web port. Server, ffmpeg and Comfy paths are configurable in `server/app/config.py`.

Optional remote LTX generation uses `TYPESET_REMOTE_COMFY_URL` plus a separate local proxy on 8190. Words, mattes, the deterministic plate, editor and export stay local. Plate PNGs upload directly to the remote ComfyUI input endpoint; generated outputs download over HTTP. Remote preflight checks node/model availability before generation. The existing local proxy on 8189 is preserved. See [remote setup](server.md#remote-comfyui) and the [GPU-host install request](gpu-host-install.md).

The SDK runner uses workflow sidecars rather than hardcoded node IDs. It polls jobs and tolerates the proxy's transient `expired` status. Large inputs are copied to `~/ComfyUI/input/typeset/<project>/`, not uploaded through the proxy. Results are collected into `data/projects/<id>/`.

## Preview and export

1. Upload footage/audio and optionally paste lyrics.
2. Word analysis runs faster-whisper on CPU. Provided lyrics are matched heuristically to recognized words; this is not acoustic forced alignment. Correct timings in the editor.
3. Foreground analysis produces RGBA PNGs, a VP9-alpha preview, and a largest-component bounding-box track. It does not perform face recognition, identity tracking or planar tracking.
4. Preview composites background → behind words → foreground cutout → overlay/anchor words. An active generated shot replaces the background and suppresses the original foreground matte for that interval.
5. Export captures the same deterministic renderer at explicit frame indices. MP4 uses the requested composite/text layer and project audio; ProRes 4444 and VP9-alpha overlays contain transparent unoccluded text. Each export has its own job directory and blocks project writes during capture for a stable project state.

A combined text overlay does not by itself reproduce mixed front/behind placements in another editor: the foreground cutout must also be layered correctly. Renderer-only `text-behind` and `text-front` modes are available for further integration.

## Generation and model scope

The initial `text_plate` workflow is **deterministic neon/chrome font compositing**, not a generative image editor. LTX-Video 2B 0.9.8 distilled animates this plate. First/last-frame morphing is delivered as a separate Comfy workflow; the initial REST generation path uses plate → I2V. Model-evaluation graphs compare learned image rendering/editing separately, before promoting a model to the production path.

Keep exact captions as rendered fonts. Generated text may change shape or spelling, even when a sampled test looks good. Small 2B clips are the practical starting point; higher resolution, 13B GGUF and image models have different speed and memory costs. See measured results rather than assuming archival warm-run timings apply to every prompt.

## Licensing and demo assets

Project code is MIT; see the root LICENSE. Bundled fonts retain their OFL notices. Model weights and third-party nodes have independent terms. The offline demo uses synthesized shapes and audio; integration speech is synthesized locally. Model-generated test content is labeled as such in the evaluation notes.
