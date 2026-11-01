// Right-panel header: where you are. Root = "Look" (the whole video); a line or group shows as a chip with ×.
import {Icon} from './icons';

export function Crumb({chip,onBack,children}:{chip?:{dot?:string;text:string;title?:string};onBack?:()=>void;children?:React.ReactNode}){
  return <div className="crumb">
    {chip?<>
      <button className="crumb-root" onClick={onBack} title="Look · whole video (esc)">Look</button>
      <span className="crumb-sep" aria-hidden="true">/</span>
      <span className="crumb-chip" title={chip.title||chip.text}>{chip.dot&&<i className={`role-dot role-${chip.dot}`}/>}<span className="crumb-text">{chip.text}</span>
        <button className="crumb-x" onClick={onBack} aria-label="Deselect" title="Deselect (esc)"><Icon name="close" size={12}/></button></span>
    </>:<span className="crumb-root at">Look</span>}
    {children&&<span className="crumb-acts">{children}</span>}
  </div>;
}
