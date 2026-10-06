/** A chat can request development, but only the frozen runner edits source. */
import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {Type} from '@earendil-works/pi-ai';
export function registerChat(pi){
  pi.registerTool({name:'development_request',label:'Create a development plan',
    description:'Only for an explicit request to build/change/fix software. Hand off a standalone faithful request to the selected planner and its clarification/research stages.',
    parameters:Type.Object({request:Type.String({minLength:1,maxLength:12000})}),
    async execute(_id,params,_signal,_update,ctx){
      if(process.env.QWEN_WORKFLOW_ROLE!=='chat')throw new Error('Chat handoff only');
      writeFileSync(join(process.env.QWEN_WORKFLOW_SESSION,'development-request.json'),JSON.stringify(params));
      return {content:[{type:'text',text:'Development request saved. The web runner will start clarification and planning.'}],details:{developmentHandoff:true}};
    }});
  pi.on('tool_result',(event,ctx)=>{
    if(process.env.QWEN_WORKFLOW_ROLE==='chat' && event.details?.developmentHandoff && !event.isError)ctx.abort();
  });
}
