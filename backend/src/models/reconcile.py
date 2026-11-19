from sqlalchemy import Column,Integer,String,Float
from src.config.database import Base
class ReconcileBatch(Base):
 __tablename__='reconcile_batches'
 id=Column(Integer,primary_key=True); batch_key=Column(String(64),unique=True); digest=Column(String(64)); run_id=Column(Integer); actor=Column(String(120)); created=Column(Float)
 required=Column(Integer); confirmed=Column(Integer); pending=Column(Integer)
class ReconcileOrder(Base):
 __tablename__='reconcile_orders'
 id=Column(Integer,primary_key=True); batch_id=Column(Integer); order_no=Column(String(60)); device=Column(String(100)); day=Column(String(10)); start=Column(Integer); end=Column(Integer)
 required=Column(Integer); confirmed=Column(Integer); pending=Column(Integer)
class ReconcileAlloc(Base):
 __tablename__='reconcile_allocations'
 id=Column(Integer,primary_key=True); batch_id=Column(Integer); order_id=Column(Integer); run_id=Column(Integer); shift_key=Column(String(20))
 device=Column(String(100)); period=Column(String(10)); start=Column(Integer); end=Column(Integer); qty=Column(Integer)
