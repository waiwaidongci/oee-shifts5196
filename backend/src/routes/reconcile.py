from fastapi import APIRouter,Depends
from src.config.database import database
from src.controllers.auth import current,editor
from src.schemas.requests import PreviewInput,ConfirmInput
from src.services import reconcile as svc
router=APIRouter()
@router.get('/reconcile/pool/{run_id}')
def pool(run_id:int,db=Depends(database),u=Depends(current)): return svc.pool(db,run_id)
@router.post('/reconcile/preview')
def preview(b:PreviewInput,db=Depends(database),u=Depends(current)): return svc.preview(db,u,b)
@router.post('/reconcile/confirm')
def confirm(b:ConfirmInput,db=Depends(database),u=Depends(editor)): return svc.confirm(db,u,b)
@router.get('/reconcile/batches')
def batches(db=Depends(database),u=Depends(current)): return svc.batches(db)
@router.get('/reconcile/batches/{id}')
def batch(id:int,db=Depends(database),u=Depends(current)): return svc.detail(db,id)
