"use client";
import { useEffect } from "react";
import { CircleAlert, CircleCheck, X } from "lucide-react";
export function Notice({message,error,onClose}:{message:string;error?:boolean;onClose?:()=>void}) {
  useEffect(()=>{ if(!onClose)return; const timer=setTimeout(onClose,6500); return ()=>clearTimeout(timer); },[message,onClose]);
  return <div role="status" className={`flex items-start gap-2 rounded-xl border px-3.5 py-3 text-sm ${error?"border-[#f3d7d7] bg-[#fff8f8] text-[#a64242]":"border-[#d7ebdf] bg-[#f5fcf7] text-[#2e7652]"}`}><span className="mt-0.5">{error?<CircleAlert size={16}/>:<CircleCheck size={16}/>}</span><p className="flex-1">{message}</p>{onClose&&<button onClick={onClose} aria-label="Dismiss"><X size={15}/></button>}</div>
}
