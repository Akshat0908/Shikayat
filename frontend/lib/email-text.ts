export function splitEmailText(body:string):{fresh:string;quoted:string} {
 const lines=body.split(/\r?\n/);
 const start=lines.findIndex((line,i)=>{
  if(/^\s*>/.test(line))return true;
  if(!/^\s*On /i.test(line))return false;
  return /\bwrote:\s*$/i.test(lines.slice(i,i+4).join("\n"));
 });
 if(start<0)return {fresh:body.trim(),quoted:''};
 return {fresh:lines.slice(0,start).join("\n").trim(),quoted:lines.slice(start).join("\n").trim()};
}
