"""Return a reusable procedure; execution and evidence are a separate responsibility."""
import json
print(json.dumps({'checks':['Initializer is invoked once with actual adapters',
 'Mouse delta is consumed once; held keys are separate', 'Fresh gesture resumes pointer lock with rejection fallback',
 'Pause, capped timestep and restart preserve input behavior', 'Computed overlay visibility and actual clicks are verified'],
 'executed':False}))
