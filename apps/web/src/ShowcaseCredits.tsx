const models = [
  {name:'MiniMax H3', href:'https://huggingface.co/Comfy-Org/MiniMax-H3', use:'Scene footage and motion from images and character references.'},
  {name:'Wan 2.2 S2V · 14B', href:'https://huggingface.co/Wan-AI/Wan2.2-S2V-14B', use:'Audio-driven singing performances in So I Die.'},
  {name:'Qwen-Image-Edit-2511', href:'https://huggingface.co/Qwen/Qwen-Image-Edit-2511', use:'Reference-image edits and the generated LOUDER lettering in Neon Rain.'},
  {name:'Z-Image-Turbo', href:'https://huggingface.co/Tongyi-MAI/Z-Image-Turbo', use:'Background stills for the star-character interludes in Angel, animated with H3.'},
  {name:'ACE-Step 1.5', href:'https://github.com/ace-step/ACE-Step-1.5', use:'The generated Neon Rain song, also used in DANCING and the text-style comparisons.'},
];

export function ShowcaseCredits(){
  return <footer className="sc-about" id="credits">
    <p>Built with <a href="https://www.comfy.org/">ComfyUI</a>. References, alternate takes, music and editable typography share one composition.</p>
    <details className="sc-credits">
      <summary>Models &amp; credits</summary>
      <dl>{models.map(m=><div key={m.name}><dt><a href={m.href}>{m.name}</a></dt><dd>{m.use}</dd></div>)}</dl>
      <p>BiRefNet supplies subject mattes; HDemucs separates vocals in the app, with BS-RoFormer used in Fall For Me preparation. MMS_FA aligns lyrics, with Whisper as a transcription fallback. YuNet supplies face detection. Tracking, audio response, text animation and compositing also use OpenCV, librosa and the Reprise renderer.</p>
      <p>Fall For Me and So I Die use artist-supplied music. The original Fall For Me star footage was composited in TouchDesigner. Generative models make footage and reference images; the text styles shown here stay editable in Reprise.</p>
      <p>Krea 2 Turbo was used in still exploration. The repository documents additional experiments, optional workflows, checkpoint variants and model licences. The code is MIT; model weights, fonts and demo media have separate terms.</p>
      <a href="https://github.com/v10101a/typeset#models-and-credits">Full model and workflow credits ↗</a>
    </details>
    <nav aria-label="Project links"><a href="https://github.com/v10101a/typeset">Source code ↗</a><a href="https://comfy.org/open-source-higgsfield">#OpenSourceHiggsfield ↗</a></nav>
  </footer>;
}
