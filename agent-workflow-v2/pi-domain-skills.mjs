/** Discover only the installed private electronics skills; retrieve bounded resources. */
import {existsSync,readFileSync,realpathSync} from 'node:fs';
import {resolve,relative,join} from 'node:path';
import {Type} from '@earendil-works/pi-ai';

const packageRoot=process.env.MYPI_DOMAIN_SKILLS || join(process.env.QWEN_WORKFLOW_TOOLKIT || process.cwd(),'../domain-skills');
const roots={
  'electronics-research':join(packageRoot,'electronics-research'),
  'kicad-mega':join(packageRoot,'kicad-pi/skills/kicad-mega'),
  'kicad-pcb-workflow':join(packageRoot,'kicad-pi/skills/kicad-pcb-workflow'),
};

export function registerDomainSkills(pi,active){
  const installed=Object.fromEntries(Object.entries(roots).filter(([,path])=>existsSync(join(path,'SKILL.md'))));
  if(!Object.keys(installed).length)return;
  pi.registerTool({name:'skill_read',label:'Private electronics skill reference',
    description:'Read a bounded page from installed electronics-research/kicad-mega/kicad-pcb-workflow; no arbitrary filesystem access.',
    parameters:Type.Object({skill:Type.Union(Object.keys(installed).map(x=>Type.Literal(x))),
      path:Type.Optional(Type.String()),offset:Type.Optional(Type.Integer({minimum:0})),
      limit:Type.Optional(Type.Integer({minimum:100,maximum:8000}))}),
    async execute(_id,params,_signal,_update,ctx){
      if(!active(ctx.model))throw new Error('Explicit private Pi workflow only');
      const base=realpathSync(installed[params.skill]);const file=realpathSync(resolve(base,params.path||'SKILL.md'));
      const rel=relative(base,file);
      if(rel.startsWith('..')||!['.md','.json','.tsv'].some(ext=>file.endsWith(ext)))throw new Error('Only text resources within the chosen skill are readable');
      const data=readFileSync(file,'utf8'),offset=params.offset||0,limit=params.limit||6000;
      return {content:[{type:'text',text:data.slice(offset,offset+limit)}],
        details:{path:file,offset,total_characters:data.length,next_offset:offset+limit<data.length?offset+limit:null}};
    }});
}

export function domainInstructions(){
  const descriptions=Object.entries(roots).filter(([,path])=>existsSync(join(path,'SKILL.md'))).map(([name,path])=>{
    const text=readFileSync(join(path,'SKILL.md'),'utf8');
    return `${name}: ${text.match(/^description:\s*(.+)$/m)?.[1]||'Installed private domain skill'}`;
  });
  return descriptions.length ? '\n\nAvailable private electronics skills (load only when relevant using skill_read):\n'+
    descriptions.join('\n')+'\nUse kicad-mega for new CAD work; the legacy skill preserves historical procedures. Read only relevant resources; native actions require explicitly declared task/test scope and verified runtime. Never claim a capability was executed merely because a skill is installed.' : '';
}
