/** Fixed arithmetic only: no expressions, eval, imports selected by input or project IO. */
import {readFileSync} from 'node:fs';

const operations={add:(a,b)=>a+b,subtract:(a,b)=>a-b,multiply:(a,b)=>a*b,
  divide:(a,b)=>a/b,min:Math.min,max:Math.max};

function finite(value) {
  if(typeof value!=='number'||!Number.isFinite(value)||Math.abs(value)>1e100)
    throw new Error('Inputs and intermediate values must be finite numbers within ±1e100.');
  return value;
}

function describe(value) {
  return {value,precision17:value.toPrecision(17),sign:value<0?-1:value>0?1:0,
    ...(Object.is(value,-0)?{negative_zero:true}:{})};
}

function trace(input) {
  const repeat=input.repeat??1,steps=input.operations;
  if(!Number.isInteger(repeat)||repeat<1||repeat>32||!Array.isArray(steps)||
      steps.length<1||steps.length>8||steps.length*repeat>32)
    throw new Error('Use 1-8 operations and at most 32 total operation results.');
  let value=finite(input.initial);const initial=describe(value),results=[];
  for(let cycle=1;cycle<=repeat;cycle++)for(const step of steps) {
    if(!Object.hasOwn(operations,step.op))throw new Error('Unsupported arithmetic operation.');
    finite(step.value);
    value=finite(operations[step.op](value,step.value));
    results.push({cycle,op:step.op,operand:step.value,...describe(value)});
  }
  return {arithmetic:'JavaScript Number (IEEE 754 binary64)',initial,results,final:describe(value),
    application_executed:false};
}

try { console.log(JSON.stringify(trace(JSON.parse(readFileSync(process.argv[2],'utf8'))))); }
catch(error) { console.error(String(error.message));process.exitCode=1; }
