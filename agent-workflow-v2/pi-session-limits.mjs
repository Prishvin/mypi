/** Explain request controls without applying a planner's limits to future workers. */
export function sessionLimits(role,env=process.env){
  const limits='\nCURRENT '+String(role||'model').toUpperCase()+' SESSION LIMITS (this model call only): input='+
    env.QWEN_WORKFLOW_INPUT_BUDGET+', total output='+env.QWEN_WORKFLOW_OUTPUT_BUDGET+
    ', thinking='+env.QWEN_WORKFLOW_THINKING+', reasoning effort='+(env.QWEN_WORKFLOW_REASONING||'provider default')+
    ', separate thinking cap='+(env.QWEN_WORKFLOW_REASONING_BUDGET_TOKENS||'none/native')+
    '. The current response output cap includes this call\'s thinking and tool arguments. ';
  if(['architect','reviewer'].includes(role))return limits+
    'These limits control producing this plan or review, not executing the tasks it describes. '+
    'Each future todo has independent task.context input, output, reasoning effort and thinking limits. '+
    'Choose those from the work and the executor\'s supported limits; preserve valid budgets unless a task-specific reason justifies a change. '+
    'Do not copy or clamp future task budgets to this session\'s limits. A future task may validly use more output or thinking tokens, or a different effort than this reviewer. '+
    'Task budgets must still satisfy their own model window, margin and native validation gates.';
  if(role==='code')return limits+
    'These execution limits were resolved from the selected frozen todo and explicit launch overrides. '+
    'Follow that frozen implementation contract; limits are ceilings, not token targets.';
  return limits+'These limits apply only to this conversation phase; they do not establish budgets for future implementation tasks.';
}
