"""Persist inline questions and one reply without invoking a model."""
import tempfile,threading,time,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store import Store
from processes import Job,Jobs
class Clarification(unittest.TestCase):
 def test_question_reply_and_pause_remain_in_shared_history(self):
  for answer in ['Use the current folder',None,False]:
   with self.subTest(answer=answer),tempfile.TemporaryDirectory() as tmp:
    store=Store(Path(tmp));row=store.create();jobs=Jobs(store);job=Job(store,row['id']);jobs.jobs[row['id']]=job
    got=[];thread=threading.Thread(target=lambda:got.append(job.dialog({'id':'question-1','method':'input','title':'Which folder?'})));thread.start()
    for _ in range(100):
     if store.get(row['id']).get('dialog'):break
     time.sleep(.01)
    jobs.answer(row['id'],'question-1',answer)
    with self.assertRaisesRegex(ValueError,'no longer pending'):jobs.answer(row['id'],'question-1','Duplicate reply')
    thread.join(timeout=2);self.assertEqual(got,[answer]);self.assertFalse(thread.is_alive())
    restored=Store(Path(tmp)).get(row['id']);notes=restored['messages']
    self.assertEqual([m['kind'] for m in notes],['clarification','clarification-answer'])
    self.assertEqual(notes[0]['text'],'Which folder?');self.assertEqual(notes[0]['dialogue_id'],notes[1]['dialogue_id'])
    self.assertEqual(notes[1]['text'],'Paused clarification' if answer is None else 'No' if answer is False else answer)
    self.assertIsNone(restored['dialog'])
