"""厂商工单跨班对账：与已复核报告按同设备、时段相交分配整数良品。

- 原报告保留：占用只写 reconcile_* 表，班次剩余=快照良品-已确认合计。
- 确认整批在同一事务内按行锁串行，按最新余量重算；并发余量变化自然生效。
- 同批重试不重复占用：batch_key 唯一，命中且内容一致直接返回原结果。
- 无解整批不占量，仅留审计，返回卡住的工单与班次。
"""
import hashlib,json,threading,time
from fastapi import HTTPException
from sqlalchemy import select
from src.models.run import Run
from src.models.reconcile import ReconcileBatch,ReconcileOrder,ReconcileAlloc
from src.services.audit import log
from src.services.flow import allocate

_locks={};_guard=threading.Lock()
def _lock(run_id):
 with _guard: return _locks.setdefault(run_id,threading.Lock())

def _approved_run(db,run_id):
 run=db.get(Run,run_id)
 if not run: raise HTTPException(404,'报告不存在')
 if not (run.status=='completed' and run.approved): raise HTTPException(409,'仅已复核报告可参与对账')
 return run

def shifts_of(run):
 """已复核报告冻结快照中的班次（原报告，不改动）。"""
 return [{'key':str(i),'device':s['department'],'day':s['period'],'start':s['start'],'end':s['end'],'good':s['good']} for i,s in enumerate(run.snapshot['sources'])]

def pool(db,run_id):
 run=_approved_run(db,run_id)
 used={}
 for a in db.query(ReconcileAlloc).filter_by(run_id=run.id).all(): used[a.shift_key]=used.get(a.shift_key,0)+a.qty
 shifts=[]
 for s in shifts_of(run):
  confirmed=used.get(s['key'],0)
  shifts.append({**s,'confirmed':confirmed,'remaining':s['good']-confirmed})
 return {'run_id':run.id,'name':run.name,'shifts':shifts}

def _orders_payload(orders):
 return [{'order_no':o.order_no,'device':o.device,'day':o.day,'start':o.start,'end':o.end,'required':o.required} for o in orders]

def _digest(run_id,orders):
 canon=sorted(orders,key=lambda o:(o['order_no'],o['device'],o['day'],o['start'],o['end'],o['required']))
 return hashlib.sha256(json.dumps({'run_id':run_id,'orders':canon},sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def _check_orders(orders):
 seen=set()
 for o in orders:
  if o['order_no'] in seen: raise HTTPException(422,'工单号在批内重复：'+o['order_no'])
  seen.add(o['order_no'])

def _shift_brief(s): return {'shift_key':s['key'],'device':s['device'],'day':s['day'],'start':s['start'],'end':s['end']}

def _result_payload(result,orders,shifts):
 if not result['feasible']:
  return {'feasible':False,'shortage':result['shortage'],
   'stuck_orders':[{'order_no':orders[i]['order_no'],'device':orders[i]['device'],'day':orders[i]['day'],'start':orders[i]['start'],'end':orders[i]['end'],'required':orders[i]['required'],'unmet':result['unmet'].get(i,0)} for i in result['stuck_orders']],
   'stuck_shifts':[{**_shift_brief(shifts[j]),'remaining':shifts[j]['remaining']} for j in result['stuck_shifts']]}
 rows=[]
 for i,o in enumerate(orders):
  allocs=[{**_shift_brief(shifts[j]),'qty':q} for (ii,j),q in sorted(result['confirmed'].items()) if ii==i]
  rows.append({'order_no':o['order_no'],'device':o['device'],'day':o['day'],'start':o['start'],'end':o['end'],'required':o['required'],'confirmed':sum(a['qty'] for a in allocs),'pending':result['pending'][i],'allocations':allocs})
 return {'feasible':True,'orders':rows,'required':sum(o['required'] for o in orders),'confirmed':sum(r['confirmed'] for r in rows),'pending':sum(r['pending'] for r in rows)}

def preview(db,user,body):
 """试算：按当前余量演示分配，不占用、不落库；确认时仍按最新余量重算。"""
 run=_approved_run(db,body.run_id)
 p=pool(db,run.id)
 orders=_orders_payload(body.orders);_check_orders(orders)
 return _result_payload(allocate(orders,p['shifts']),orders,p['shifts'])

def confirm(db,user,body):
 run=_approved_run(db,body.run_id)
 orders=_orders_payload(body.orders);_check_orders(orders)
 digest=_digest(run.id,orders)
 with _lock(run.id):
  db.execute(select(Run).where(Run.id==run.id).with_for_update())
  existing=db.query(ReconcileBatch).filter_by(batch_key=body.batch_key).first()
  if existing:
   if existing.digest!=digest: raise HTTPException(409,'批次键已被不同内容的工单批使用')
   return {**detail(db,existing.id),'replayed':True}
  p=pool(db,run.id)
  result=allocate(orders,p['shifts'])
  if not result['feasible']:
   log(db,user.email,'reconcile.rejected',{'batch_key':body.batch_key,'shortage':result['shortage']})
   db.commit()
   return _result_payload(result,orders,p['shifts'])
  payload=_result_payload(result,orders,p['shifts'])
  batch=ReconcileBatch(batch_key=body.batch_key,digest=digest,run_id=run.id,actor=user.email,created=time.time(),required=payload['required'],confirmed=payload['confirmed'],pending=payload['pending'])
  db.add(batch);db.flush()
  for i,o in enumerate(orders):
   row=payload['orders'][i]
   rec=ReconcileOrder(batch_id=batch.id,order_no=o['order_no'],device=o['device'],day=o['day'],start=o['start'],end=o['end'],required=o['required'],confirmed=row['confirmed'],pending=row['pending'])
   db.add(rec);db.flush()
   for a in row['allocations']:
    db.add(ReconcileAlloc(batch_id=batch.id,order_id=rec.id,run_id=run.id,shift_key=a['shift_key'],device=a['device'],period=a['day'],start=a['start'],end=a['end'],qty=a['qty']))
  log(db,user.email,'reconcile.confirm',{'batch_key':body.batch_key,'confirmed':payload['confirmed'],'pending':payload['pending']})
  db.commit()
  return {**detail(db,batch.id),'feasible':True}

def detail(db,batch_id):
 batch=db.get(ReconcileBatch,batch_id)
 if not batch: raise HTTPException(404,'对账批次不存在')
 orders=[]
 for o in db.query(ReconcileOrder).filter_by(batch_id=batch.id).order_by(ReconcileOrder.id).all():
  allocs=[{'shift_key':a.shift_key,'device':a.device,'day':a.period,'start':a.start,'end':a.end,'qty':a.qty} for a in db.query(ReconcileAlloc).filter_by(order_id=o.id).order_by(ReconcileAlloc.id).all()]
  orders.append({'order_no':o.order_no,'device':o.device,'day':o.day,'start':o.start,'end':o.end,'required':o.required,'confirmed':o.confirmed,'pending':o.pending,'allocations':allocs})
 return {'id':batch.id,'batch_key':batch.batch_key,'run_id':batch.run_id,'actor':batch.actor,'created':batch.created,'required':batch.required,'confirmed':batch.confirmed,'pending':batch.pending,'feasible':True,'orders':orders}

def batches(db):
 return [{'id':b.id,'batch_key':b.batch_key,'run_id':b.run_id,'actor':b.actor,'created':b.created,'required':b.required,'confirmed':b.confirmed,'pending':b.pending} for b in db.query(ReconcileBatch).order_by(ReconcileBatch.id.desc()).all()]
