"""工单对账端到端 API 测试：登录、班次余量、试算、确认、幂等重试、权限与校验。
运行：python3 backend/tests/test_api.py
"""
import os,sys,time,types
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
DB='/tmp/recon_api_test.db'
if os.path.exists(DB): os.remove(DB)
st=types.ModuleType('src.config.settings')
st.CONFIG={'title':'t','slug':'t'}
st.DATABASE_URL='sqlite:///'+DB;st.REDIS_URL='redis://localhost:6379/0';st.SECRET='test-secret'
sys.modules['src.config.settings']=st

from fastapi.testclient import TestClient
from src.config.database import Base,engine,Session
from src.models import identity,source,run,reconcile as reconcile_model
from src.models.identity import User
from src.models.run import Run
from src.utils.security import password_hash
from src.main import app

Base.metadata.create_all(engine)
SOURCES=[
 {'department':'试制机A','period':'2026-11-17','start':480,'end':1020,'ideal_seconds':25,'total':120,'good':100,'downtime':[]},
 {'department':'试制机A','period':'2026-11-17','start':1020,'end':1560,'ideal_seconds':25,'total':120,'good':100,'downtime':[]},
 {'department':'试制机B','period':'2026-11-17','start':480,'end':1020,'ideal_seconds':25,'total':60,'good':50,'downtime':[]}]
with Session() as db:
 for role in ('admin','analyst','viewer'):
  db.add(User(email=role+'@demo.local',role=role,password=password_hash('Demo2026!')))
 db.add(Run(name='seed-十一月核算',status='completed',snapshot={'policy':{},'sources':SOURCES,'period':'全部'},checksum='x',created=time.time(),approved=True,review='ok'))
 db.commit()

c=TestClient(app)
def login(email):
 r=c.post('/auth/login',json={'email':email,'password':'Demo2026!'})
 assert r.status_code==200,r.text
 return {'Authorization':'Bearer '+r.json()['token']}
ADMIN=login('admin@demo.local');ANALYST=login('analyst@demo.local');VIEWER=login('viewer@demo.local')

def test_api():
 # 未登录拒绝
 assert c.get('/reconcile/batches').status_code==401
 # 班次余量
 r=c.get('/reconcile/pool/1',headers=VIEWER)
 assert r.status_code==200,r.text
 pool=r.json();assert pool['name']=='seed-十一月核算'
 assert [(s['good'],s['remaining']) for s in pool['shifts']]==[(100,100),(100,100),(50,50)]
 # 未复核报告拒绝对账
 with Session() as db:
  db.add(Run(name='draft',status='completed',snapshot={'policy':{},'sources':SOURCES,'period':'全部'},checksum='y',created=time.time(),approved=False,review=''))
  db.commit()
 assert c.get('/reconcile/pool/2',headers=ADMIN).status_code==409
 # 试算：跨班多分法
 order={'order_no':'PO-1','device':'试制机A','day':'2026-11-17','start':900,'end':1200,'required':150}
 r=c.post('/reconcile/preview',headers=ANALYST,json={'run_id':1,'orders':[order]})
 assert r.status_code==200,r.text
 p=r.json();assert p['feasible'] and p['confirmed']==100 and p['pending']==50,p
 # 确认占用
 r=c.post('/reconcile/confirm',headers=ANALYST,json={'run_id':1,'batch_key':'api-batch-001','orders':[order]})
 assert r.status_code==200,r.text
 conf=r.json();assert conf['feasible'] and conf['id'] and conf['confirmed']==100
 # 同批重试不重复占用
 r=c.post('/reconcile/confirm',headers=ANALYST,json={'run_id':1,'batch_key':'api-batch-001','orders':[order]})
 assert r.json()['id']==conf['id'] and r.json().get('replayed')
 r=c.get('/reconcile/pool/1',headers=ADMIN)
 assert [s['remaining'] for s in r.json()['shifts']]==[50,50,50],'重试后余量不变'
 # viewer 无确认权限
 r=c.post('/reconcile/confirm',headers=VIEWER,json={'run_id':1,'batch_key':'api-batch-002','orders':[order]})
 assert r.status_code==403
 # 批次列表与归属明细
 r=c.get('/reconcile/batches',headers=VIEWER)
 assert len(r.json())==1 and r.json()[0]['batch_key']=='api-batch-001'
 r=c.get('/reconcile/batches/'+str(conf['id']),headers=VIEWER)
 d=r.json();assert d['orders'][0]['pending']==50
 assert {a['qty'] for a in d['orders'][0]['allocations']}=={50}
 # 无解：整批不占量并指出卡住工单班次
 big={'order_no':'PO-2','device':'试制机A','day':'2026-11-17','start':480,'end':1560,'required':200}
 r=c.post('/reconcile/confirm',headers=ADMIN,json={'run_id':1,'batch_key':'api-batch-003','orders':[big]})
 assert r.status_code==200,r.text
 rej=r.json();assert not rej['feasible'] and rej['shortage']==100
 assert [o['order_no'] for o in rej['stuck_orders']]==['PO-2'] and len(rej['stuck_shifts'])==2
 r=c.get('/reconcile/batches',headers=ADMIN)
 assert len(r.json())==1,'无解批次不落库'
 # 校验：结束早于开始 / 需求非正 / 设备缺失
 bad=dict(order);bad['end']=100
 assert c.post('/reconcile/preview',headers=ADMIN,json={'run_id':1,'orders':[bad]}).status_code==422
 bad=dict(order);bad['required']=0
 assert c.post('/reconcile/preview',headers=ADMIN,json={'run_id':1,'orders':[bad]}).status_code==422
 bad=dict(order);bad['day']='2026-13-40'
 assert c.post('/reconcile/preview',headers=ADMIN,json={'run_id':1,'orders':[bad]}).status_code==422
 # 批内工单号重复
 assert c.post('/reconcile/preview',headers=ADMIN,json={'run_id':1,'orders':[order,order]}).status_code==422
 print('端到端 API 用例通过')

if __name__=='__main__':
 test_api()
 print('全部 API 测试通过')
