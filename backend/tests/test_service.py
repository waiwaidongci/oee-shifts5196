"""工单对账服务层测试（SQLite 落库）：确认占用、同批幂等、余量重算、无解不占量、并发。
运行：python3 backend/tests/test_service.py
"""
import os,sys,time,types,threading
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
DB='/tmp/recon_svc_test.db'
if os.path.exists(DB): os.remove(DB)
# 注入测试配置，避免依赖 /app/project.json 与环境变量
st=types.ModuleType('src.config.settings')
st.CONFIG={'title':'t'};st.DATABASE_URL='sqlite:///'+DB;st.REDIS_URL='redis://localhost:6379/0';st.SECRET='test'
sys.modules['src.config.settings']=st

from src.config.database import Base,engine,Session
from src.models import identity,source,run,reconcile as reconcile_model
from src.models.run import Run
from src.models.reconcile import ReconcileBatch,ReconcileOrder,ReconcileAlloc
from src.services import reconcile as svc
from fastapi import HTTPException

Base.metadata.create_all(engine)
USER=SimpleNamespace(email='analyst@demo.local',role='analyst')

def mkrun(name,sources):
 with Session() as db:
  obj=Run(name=name,status='completed',snapshot={'policy':{},'sources':sources,'period':'全部'},checksum='x',created=time.time(),approved=True,review='ok')
  db.add(obj);db.commit();return obj.id

def body(run_id,key,orders):
 return SimpleNamespace(run_id=run_id,batch_key=key,orders=[SimpleNamespace(**o) for o in orders])

def test_confirm_and_replay():
 rid=mkrun('r1',[
  {'department':'试制机A','period':'2026-11-17','start':480,'end':1020,'ideal_seconds':25,'total':120,'good':100,'downtime':[]},
  {'department':'试制机A','period':'2026-11-17','start':1020,'end':1560,'ideal_seconds':25,'total':120,'good':100,'downtime':[]}])
 orders=[{'order_no':'W1','device':'试制机A','day':'2026-11-17','start':480,'end':1560,'required':150}]
 with Session() as db:
  r=svc.confirm(db,USER,body(rid,'batch-key-0001',orders))
  assert r['feasible'] and r['confirmed']==100 and r['pending']==50,r
  bid=r['id']
  allocs={a['shift_key']:a['qty'] for a in r['orders'][0]['allocations']}
  assert allocs=={'0':50,'1':50},allocs
 with Session() as db:
  p=svc.pool(db,rid)
  assert [s['remaining'] for s in p['shifts']]==[50,50],'确认后剩余应为50/50'
 # 同批重试：返回原批次，不重复占用
 with Session() as db:
  r2=svc.confirm(db,USER,body(rid,'batch-key-0001',orders))
  assert r2['id']==bid and r2.get('replayed'),r2
 with Session() as db:
  assert db.query(ReconcileBatch).count()==1
  assert db.query(ReconcileAlloc).filter_by(run_id=rid).count()==2
  p=svc.pool(db,rid)
  assert [s['remaining'] for s in p['shifts']]==[50,50],'重试不得重复占用'
 # 同键不同内容：拒绝
 try:
  with Session() as db: svc.confirm(db,USER,body(rid,'batch-key-0001',[{'order_no':'W1','device':'试制机A','day':'2026-11-17','start':480,'end':1560,'required':99}]))
  raise AssertionError('同键不同内容应拒绝')
 except HTTPException as e:
  assert e.status_code==409
 # 第二批占用剩余
 with Session() as db:
  r3=svc.confirm(db,USER,body(rid,'batch-key-0002',[{'order_no':'W2','device':'试制机A','day':'2026-11-17','start':480,'end':1020,'required':50}]))
  assert r3['feasible'] and r3['confirmed']==50 and r3['pending']==0
 with Session() as db:
  p=svc.pool(db,rid)
  assert [s['remaining'] for s in p['shifts']]==[0,50]
 # 无解：整批不占量，指出卡住工单与班次
 with Session() as db:
  r4=svc.confirm(db,USER,body(rid,'batch-key-0003',[{'order_no':'W3','device':'试制机A','day':'2026-11-17','start':480,'end':1560,'required':100}]))
  assert not r4['feasible'] and r4['shortage']==50,r4
  assert [o['order_no'] for o in r4['stuck_orders']]==['W3']
  assert {s['shift_key'] for s in r4['stuck_shifts']}=={'0','1'}
 with Session() as db:
  assert db.query(ReconcileBatch).count()==2,'无解批次不落库'
  p=svc.pool(db,rid)
  assert [s['remaining'] for s in p['shifts']]==[0,50],'无解整批不占量'
 # 试算不落库
 with Session() as db:
  pv=svc.preview(db,USER,body(rid,'batch-key-0004',[{'order_no':'W4','device':'试制机A','day':'2026-11-17','start':1020,'end':1560,'required':50}]))
  assert pv['feasible'] and pv['confirmed']==50
  assert db.query(ReconcileBatch).count()==2,'试算不得落库'
 print('确认/幂等/无解/试算用例通过')

def test_concurrent_confirm():
 rid=mkrun('r2',[{'department':'试制机B','period':'2026-11-18','start':480,'end':1020,'ideal_seconds':25,'total':1100,'good':1000,'downtime':[]}])
 results={};errors=[]
 def work(k):
  try:
   with Session() as db:
    results[k]=svc.confirm(db,USER,body(rid,f'conc-{k%8:02d}-key',[{'order_no':f'CW{k}','device':'试制机B','day':'2026-11-18','start':480,'end':1020,'required':200}]))
  except Exception as e: errors.append(e)
 threads=[threading.Thread(target=work,args=(k,)) for k in range(8)]
 [t.start() for t in threads];[t.join() for t in threads]
 assert not errors,[str(e) for e in errors]
 ok=[r for r in results.values() if r['feasible']]
 assert len(ok)==5,f'1000良品/每批200 应恰好5批成功，实际{len(ok)}'
 with Session() as db:
  total=sum(a.qty for a in db.query(ReconcileAlloc).filter_by(run_id=rid).all())
  assert total==1000,f'并发确认总占用{total}应等于1000'
  assert db.query(ReconcileBatch).filter_by(run_id=rid).count()==5
 # 并发同批重试：只建一批，不重复占用
 rid3=mkrun('r3',[{'department':'试制机C','period':'2026-11-19','start':480,'end':1020,'ideal_seconds':25,'total':120,'good':100,'downtime':[]}])
 ids={};errs=[]
 def retry():
  try:
   with Session() as db:
    r=svc.confirm(db,USER,body(rid3,'conc-same-key',[{'order_no':'CX','device':'试制机C','day':'2026-11-19','start':480,'end':1020,'required':10}]))
    ids[r['id']]=ids.get(r['id'],0)+1
  except Exception as e: errs.append(e)
 ts=[threading.Thread(target=retry) for _ in range(4)]
 [t.start() for t in ts];[t.join() for t in ts]
 assert not errs,[str(e) for e in errs]
 assert len(ids)==1,f'并发同批应只建一批，实际{ids}'
 with Session() as db:
  total=sum(a.qty for a in db.query(ReconcileAlloc).filter_by(run_id=rid3).all())
  assert total==10,f'同批并发重试占用{total}应为10，不得重复占用'
 print('并发确认用例通过')

if __name__=='__main__':
 test_confirm_and_replay()
 test_concurrent_confirm()
 print('全部服务层测试通过')
