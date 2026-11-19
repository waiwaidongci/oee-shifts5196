"""跨班对账分配算法测试：手算用例 + 暴力枚举对拍。
运行：python3 backend/tests/test_flow.py
"""
import random,sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.services.flow import allocate,abs_minutes


def eligible(o,s):
 return o['device']==s['device'] and max(abs_minutes(o['day'],o['start']),abs_minutes(s['day'],s['start']))<min(abs_minutes(o['day'],o['end']),abs_minutes(s['day'],s['end']))


def brute(orders,shifts):
 """暴力枚举全部整数分法，返回(全部分法, 最大可分配总量)。"""
 n,m=len(orders),len(shifts)
 pairs=[(i,j) for i in range(n) for j in range(m) if eligible(orders[i],shifts[j])]
 sols=[];best=0;cur=[0]*len(pairs)
 orem=[o['required'] for o in orders];srem=[s['remaining'] for s in shifts]
 def rec(k,total):
  nonlocal best
  if k==len(pairs):
   best=max(best,total)
   if all(r==0 for r in orem): sols.append(list(cur))
   return
  i,j=pairs[k]
  for x in range(min(orem[i],srem[j])+1):
   cur[k]=x;orem[i]-=x;srem[j]-=x
   rec(k+1,total+x)
   orem[i]+=x;srem[j]+=x
 rec(0,0)
 return sols,best


def check_against_brute(orders,shifts):
 res=allocate(orders,shifts)
 sols,best=brute(orders,shifts)
 total=sum(o['required'] for o in orders)
 if not sols:
  assert not res['feasible'],'应无解却判可行'
  assert res['shortage']==total-best,'缺口应等于需求-最大可分配'
  so,ss=set(res['stuck_orders']),set(res['stuck_shifts'])
  assert so,'无解时应有卡住工单'
  assert sum(orders[i]['required'] for i in so)-sum(shifts[j]['remaining'] for j in ss)==res['shortage'],'最小割恒等式'
  for i in so:
   for j in range(len(shifts)):
    if eligible(orders[i],shifts[j]): assert j in ss,'卡住工单的可用班次应都在卡住班次中'
  return
 assert res['feasible'],'应有解却判无解'
 pairs=[(i,j) for i in range(len(orders)) for j in range(len(shifts)) if eligible(orders[i],shifts[j])]
 for k,(i,j) in enumerate(pairs):
  want=min(s[k] for s in sols)
  got=res['confirmed'].get((i,j),0)
  assert got==want,f'({i},{j}) 共有数量 {got} != 暴力最小 {want}'
 for i,o in enumerate(orders):
  assert res['pending'][i]==o['required']-sum(q for (a,_),q in res['confirmed'].items() if a==i),'待核=需求-确认合计'
 for j in range(len(shifts)):
  assert sum(q for (a,b),q in res['confirmed'].items() if b==j)<=shifts[j]['remaining'],'每班不超剩余良品'


def test_hand_cases():
 # 多分法：两班各剩100，工单需150 -> 每班共有50，待核50
 shifts=[{'key':'0','device':'A','day':'2026-11-17','start':480,'end':1020,'remaining':100},
         {'key':'1','device':'A','day':'2026-11-17','start':1020,'end':1560,'remaining':100}]
 orders=[{'order_no':'W1','device':'A','day':'2026-11-17','start':480,'end':1560,'required':150}]
 r=allocate(orders,shifts)
 assert r['feasible'] and r['confirmed']=={(0,0):50,(0,1):50} and r['pending']=={0:50},r
 # 唯一分法：只一个班相交
 shifts2=[{'key':'0','device':'A','day':'2026-11-17','start':480,'end':1020,'remaining':100},
          {'key':'1','device':'B','day':'2026-11-17','start':480,'end':1020,'remaining':100}]
 orders2=[{'order_no':'W1','device':'A','day':'2026-11-17','start':600,'end':900,'required':60}]
 r=allocate(orders2,shifts2)
 assert r['feasible'] and r['confirmed']=={(0,0):60} and r['pending']=={0:0},r
 # 链式争抢：W1只能用s0；W2可用s0/s1；s0剩6,s1剩5 -> (W2,s1)共有4，待核1
 shifts3=[{'key':'0','device':'A','day':'2026-11-17','start':480,'end':1020,'remaining':6},
          {'key':'1','device':'A','day':'2026-11-17','start':1020,'end':1560,'remaining':5}]
 orders3=[{'order_no':'W1','device':'A','day':'2026-11-17','start':480,'end':1020,'required':5},
          {'order_no':'W2','device':'A','day':'2026-11-17','start':480,'end':1560,'required':5}]
 r=allocate(orders3,shifts3)
 assert r['feasible'] and r['confirmed']=={(0,0):5,(1,1):4} and r['pending']=={0:0,1:1},r
 # 无解：余量不足
 r=allocate([{'order_no':'W1','device':'A','day':'2026-11-17','start':480,'end':1020,'required':10}],
            [{'key':'0','device':'A','day':'2026-11-17','start':480,'end':1020,'remaining':6}])
 assert not r['feasible'] and r['shortage']==4 and r['stuck_orders']==[0] and r['stuck_shifts']==[0] and r['unmet']=={0:4},r
 # 无解：设备不匹配，无可用班次
 r=allocate([{'order_no':'W1','device':'X','day':'2026-11-17','start':480,'end':1020,'required':10}],
            [{'key':'0','device':'Y','day':'2026-11-17','start':480,'end':1020,'remaining':50}])
 assert not r['feasible'] and r['stuck_orders']==[0] and r['stuck_shifts']==[] and r['shortage']==10,r
 # 跨日相交：班次首日1200-2000分，工单次日480-1020分 -> 绝对时段相交
 r=allocate([{'order_no':'W1','device':'A','day':'2026-11-18','start':480,'end':1020,'required':5}],
            [{'key':'0','device':'A','day':'2026-11-17','start':1200,'end':2000,'remaining':5}])
 assert r['feasible'] and r['confirmed']=={(0,0):5},r
 # 端点相接不相交
 r=allocate([{'order_no':'W1','device':'A','day':'2026-11-17','start':1020,'end':1560,'required':5}],
            [{'key':'0','device':'A','day':'2026-11-17','start':480,'end':1020,'remaining':5}])
 assert not r['feasible'],r
 print('手算用例通过')


def test_oracle():
 rng=random.Random(20261119)
 days=['2026-11-17','2026-11-18']
 for t in range(400):
  n,m=rng.randint(1,3),rng.randint(1,3)
  orders=[];shifts=[]
  for i in range(n):
   a=rng.choice([0,300,480,900,1020]);b=a+rng.choice([120,300,540,960])
   orders.append({'order_no':f'W{i}','device':rng.choice('AB'),'day':rng.choice(days),'start':a,'end':b,'required':rng.randint(1,3)})
  for j in range(m):
   a=rng.choice([0,480,1020]);b=a+rng.choice([300,540,960])
   shifts.append({'key':str(j),'device':rng.choice('AB'),'day':rng.choice(days),'start':a,'end':b,'remaining':rng.randint(0,3)})
  check_against_brute(orders,shifts)
 print('暴力对拍 400 例通过')


if __name__=='__main__':
 test_hand_cases()
 test_oracle()
 print('全部算法测试通过')
