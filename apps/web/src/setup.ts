export type SetupTab='demo'|'local'|'cloud'|'models';
export const SETUP_EVENT='reprise:setup';
export function openSetup(tab:SetupTab='demo'){window.dispatchEvent(new CustomEvent(SETUP_EVENT,{detail:tab}));}

export type GenerationPreset={id:string;name:string;task:string;description:string;file:string;requirements:string;models:string;guide:string};
export const GENERATION_PRESETS:GenerationPreset[]=[
  {id:'zimage',name:'Z-Image Turbo',task:'Create an image',description:'Make a new still from a text prompt. Start here before animating it.',file:'starter_zimage.api.json',requirements:'3 model files · core ComfyUI nodes',models:'https://huggingface.co/Comfy-Org/z_image_turbo',guide:'https://docs.comfy.org/tutorials/image/z-image/z-image-turbo'},
  {id:'h3',name:'MiniMax H3',task:'Animate an image',description:'Turn a reference image into a short video. Large video model; a capable GPU or Cloud is recommended.',file:'minimax_remote_i2v.api.json',requirements:'5 model files · VideoHelperSuite',models:'https://huggingface.co/Comfy-Org/MiniMax-H3',guide:'https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite'},
  {id:'s2v',name:'Wan 2.2 S2V',task:'Make a singing take',description:'Animate a portrait to a vocal excerpt. Large video model; a capable GPU or Cloud is recommended.',file:'starter_s2v.api.json',requirements:'4 model files · VideoHelperSuite',models:'https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged',guide:'https://docs.comfy.org/tutorials/video/wan/wan2_2'},
];
