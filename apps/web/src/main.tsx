import ReactDOM from 'react-dom/client';
import App from './App';
import {at} from './base';
import './style.css';
// Root-absolute fetches ('/api/…', '/sample/…') resolve under the mount point (e.g. ComfyUI's /typeset).
const fetchAtRoot=window.fetch.bind(window);
window.fetch=(input,init)=>fetchAtRoot(typeof input==='string'?at(input):input,init);
ReactDOM.createRoot(document.getElementById('root')!).render(<App/>);
