import test from 'node:test';
import assert from 'node:assert/strict';
import {conversationLink,queueState} from '../static/navigation.js';
const id='a'.repeat(24),other='b'.repeat(24);
test('a localhost share link uses the configured LAN address and exact conversation',()=>{
 const link=new URL(conversationLink(id,'http://127.0.0.1:8099','http://192.168.1.34:8099'));
 assert.equal(link.origin,'http://192.168.1.34:8099');assert.equal(link.searchParams.get('conversation'),id);
 assert.throws(()=>conversationLink('../source','http://127.0.0.1:8099'),/Invalid/);
});
test('LAN visitors retain their reachable origin and conversation id',()=>{
 assert.equal(new URL(conversationLink(id,'http://192.168.1.50:8099','http://192.168.1.34:8099')).origin,'http://192.168.1.50:8099');
});
test('idle, running elsewhere and queued state are distinct',()=>{
 assert.equal(queueState([],id).busy,false);
 const active={id:other,busy:true,status:'Model generating',title:'Other chat'};
 let result=queueState([active],id);assert.equal(result.active,other);assert.equal(result.waiting,false);assert.match(result.label,/Other chat/);
 result=queueState([active,{id,busy:true,status:'Queued',title:'My chat'}],id);
 assert.equal(result.queued,1);assert.equal(result.waiting,true);assert.match(result.label,/Your query is waiting/);
});
test('a clarification hold is busy and exposes the active chat to open',()=>{
 const result=queueState([{id:other,busy:true,status:'Waiting for your clarification',title:'Research'}],id);
 assert.equal(result.active,other);assert.match(result.label,/Waiting for your clarification/);
});
