"""Normalize equivalent planner metadata; retain every behavioral contract."""
import copy
import json


def canonical(proposal):
    """Reject ambiguity and canonicalize names, references and flags, preserving meaning."""
    plan=copy.deepcopy(proposal)
    for alias,key in [('architecture_notes','architecture'),('todos','tasks')]:
        if alias not in plan:continue
        value=plan[alias]
        if alias=='architecture_notes' and not isinstance(value,(str,dict)):
            raise ValueError('Architecture notes must be text or a structured object')
        if alias=='todos' and not isinstance(value,list):
            raise ValueError('Todo alias must contain a task list')
        if alias=='architecture_notes' and isinstance(value,dict):
            if not value:raise ValueError('Architecture notes must be nonempty')
            value=json.dumps(value,ensure_ascii=False,indent=2)
        if key in plan and plan[key]!=value:
            raise ValueError('Conflicting canonical and alias plan fields: '+key)
        plan[key]=value;del plan[alias]
        plan.setdefault('schema_normalization',[]).append({'from':alias,'to':key})
    for index,task in enumerate(plan.get('tasks',[])):
        acceptance=task.get('acceptance')
        if isinstance(acceptance,dict) and all(k in acceptance for k in ('id','given','when','then')):
            task['acceptance']=[acceptance]
            plan.setdefault('schema_normalization',[]).append({'field':f'tasks[{index}].acceptance','from':'single criterion object','to':'criterion array'})
        coverage=task.get('coverage')
        if isinstance(coverage,dict):
            entries=[]
            for key,value in coverage.items():
                indices=[value] if type(value) is int else value
                if not isinstance(key,str) or not isinstance(indices,list) or not indices or not all(type(v) is int for v in indices):
                    raise ValueError('Coverage mapping requires criterion IDs and integer test indices')
                entries.extend({'criterion':key,'test':index} for index in indices)
            task['coverage']=entries
            plan.setdefault('schema_normalization',[]).append({'field':f'tasks[{index}].coverage','from':'mapping','to':'criterion/test rows'})
        context=task.get('context',{});symbols=context.get('symbols',[])
        if type(context.get('thinking')) is bool:
            context['thinking']='on' if context['thinking'] else 'off'
            plan.setdefault('schema_normalization',[]).append({'field':f'tasks[{index}].context.thinking','from':'boolean','to':'on/off'})
        if context.get('thinking')=='off' and type(context.get('reasoning_budget_tokens')) is int and context['reasoning_budget_tokens']==0:
            del context['reasoning_budget_tokens']
            plan.setdefault('schema_normalization',[]).append({'field':f'tasks[{index}].context.reasoning_budget_tokens','from':'zero with thinking off','to':'omitted; thinking remains off'})
        converted=[]
        for symbol in symbols:
            if isinstance(symbol,dict):converted.append(symbol);continue
            if not isinstance(symbol,list) or len(symbol)!=2 or not all(isinstance(s,str) for s in symbol):
                raise ValueError('Symbol pairs require exactly a path and qualified name')
            converted.append({'path':symbol[0],'name':symbol[1]})
        if converted!=symbols:
            context['symbols']=converted
            plan.setdefault('schema_normalization',[]).append({'field':f'tasks[{index}].context.symbols','from':'path/name pairs','to':'path/name objects'})
    return plan
