from datetime import date
from pydantic import BaseModel,Field,field_validator,model_validator
class Login(BaseModel): email:str; password:str
class DataInput(BaseModel): data:dict
class RunInput(BaseModel): name:str=Field(min_length=2,max_length=120); policy_id:int; period:str='全部'
class ReviewInput(BaseModel): note:str=Field(min_length=4,max_length=2000)
class ScheduleInput(BaseModel): name:str=Field(min_length=2,max_length=120); run_id:int; interval_seconds:int=Field(ge=5,le=86400)
class OrderInput(BaseModel):
 order_no:str=Field(min_length=1,max_length=60); device:str=Field(min_length=1,max_length=100); day:str=Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
 start:int=Field(ge=0); end:int=Field(le=2880); required:int=Field(ge=1)
 @field_validator('day')
 @classmethod
 def real_day(cls,v):
  date.fromisoformat(v); return v
 @model_validator(mode='after')
 def window(self):
  if self.end<=self.start: raise ValueError('工单结束分钟需晚于开始分钟')
  return self
class PreviewInput(BaseModel): run_id:int; orders:list[OrderInput]=Field(min_length=1,max_length=100)
class ConfirmInput(PreviewInput): batch_key:str=Field(min_length=8,max_length=64)
