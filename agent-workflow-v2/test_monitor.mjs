import test from 'node:test';
import assert from 'node:assert/strict';
import {number,gib,duration,phase,completion,testState} from '../pi-web/static/monitor-format.mjs';
test('Unavailable measurements remain unavailable, zero stays zero',()=>{for(const x of [undefined,null,NaN,'3']){assert.equal(number(x),'—');assert.equal(gib(x),'—');assert.equal(duration(x),'—');}assert.equal(number(0),'0');assert.equal(gib(1024**3),'1.00 GiB');});
test('Elapsed durations and completion limits do not fabricate progress',()=>{assert.equal(duration(61),'1m 1s');assert.equal(duration(3661),'1h 1m');assert.equal(duration(-1),'0s');assert.equal(completion(5,10),50);assert.equal(completion(99,10),100);assert.equal(completion(0,0),0);});
test('Test success becomes stale after source changes',()=>{assert.equal(testState(undefined),'Not run');assert.equal(testState({exit_code:0},false),'Stale');assert.equal(testState({exit_code:1},true),'Failed');assert.equal(testState({exit_code:0},true),'Passed');assert.equal(phase('reasoning'),'Thinking');});
