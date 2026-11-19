"""跨班良品对账分配算法（纯函数，不依赖配置与数据库）。

规则：同设备、时段相交的班次才可分配；整数良品；每张工单凑足；每班不超剩余良品。
先用最大流判定整批可行性；可行时逐边求"各种分法共有的数量"
（该边在所有最大流中的最小流量），余量待核；不可行时给出最小割卡住的工单与班次。
"""
from datetime import date


def abs_minutes(day, minute):
    """日期(YYYY-MM-DD)+当日分钟 -> 绝对分钟，跨日班次可正确相交。"""
    return date.fromisoformat(day).toordinal() * 1440 + minute


class Dinic:
    """整数容量最大流；弧表即残量网络，容量随求解就地变化。"""

    def __init__(self, n):
        self.n = n
        self.g = [[] for _ in range(n)]

    def add(self, u, v, c):
        self.g[u].append([v, c, len(self.g[v])])
        self.g[v].append([u, 0, len(self.g[u]) - 1])

    def maxflow(self, s, t):
        flow = 0
        n = self.n
        while True:
            level = [-1] * n
            level[s] = 0
            q = [s]
            for x in q:
                for e in self.g[x]:
                    if e[1] > 0 and level[e[0]] < 0:
                        level[e[0]] = level[x] + 1
                        q.append(e[0])
            if level[t] < 0:
                return flow
            it = [0] * n

            def dfs(x, f):
                if x == t:
                    return f
                while it[x] < len(self.g[x]):
                    e = self.g[x][it[x]]
                    if e[1] > 0 and level[e[0]] == level[x] + 1:
                        d = dfs(e[0], min(f, e[1]))
                        if d:
                            e[1] -= d
                            self.g[e[0]][e[2]][1] += d
                            return d
                    it[x] += 1
                return 0

            while True:
                f = dfs(s, 1 << 62)
                if not f:
                    break
                flow += f


def allocate(orders, shifts):
    """orders: [{order_no,device,day,start,end,required}]；
    shifts: [{key,device,day,start,end,remaining}]。
    可行 -> {'feasible':True,'confirmed':{(i,j):qty},'pending':{i:qty}}
    无解 -> {'feasible':False,'shortage':缺口,'stuck_orders':[i],'stuck_shifts':[j],'unmet':{i:qty}}
    """
    n, m = len(orders), len(shifts)
    N = n + m + 2
    S, T = 0, N - 1
    ow = [(abs_minutes(o['day'], o['start']), abs_minutes(o['day'], o['end'])) for o in orders]
    sw = [(abs_minutes(s['day'], s['start']), abs_minutes(s['day'], s['end'])) for s in shifts]
    din = Dinic(N)
    for i, o in enumerate(orders):
        din.add(S, 1 + i, o['required'])
    edge_at = {}
    for i, o in enumerate(orders):
        for j, s in enumerate(shifts):
            if o['device'] == s['device'] and max(ow[i][0], sw[j][0]) < min(ow[i][1], sw[j][1]):
                edge_at[(i, j)] = len(din.g[1 + i])
                din.add(1 + i, 1 + n + j, o['required'])
    for j, s in enumerate(shifts):
        din.add(1 + n + j, T, s['remaining'])
    total = sum(o['required'] for o in orders)
    flow = din.maxflow(S, T)
    if flow < total:
        # 残量网络中源点可达集即最小割：卡住工单=可达工单，卡住班次=可达且已占满班次
        seen = [False] * N
        seen[S] = True
        stack = [S]
        while stack:
            x = stack.pop()
            for e in din.g[x]:
                if e[1] > 0 and not seen[e[0]]:
                    seen[e[0]] = True
                    stack.append(e[0])
        return {
            'feasible': False,
            'shortage': total - flow,
            'stuck_orders': [i for i in range(n) if seen[1 + i]],
            'stuck_shifts': [j for j in range(m) if seen[1 + n + j]],
            'unmet': {i: din.g[S][i][1] for i in range(n) if din.g[S][i][1] > 0},
        }
    arcs = [(u, e[0], e[1]) for u in range(N) for e in din.g[u] if e[1] > 0]
    confirmed = {}
    for (i, j), pos in edge_at.items():
        f_e = orders[i]['required'] - din.g[1 + i][pos][1]
        if f_e <= 0:
            continue
        a, b = 1 + i, 1 + n + j
        # 该边在所有最大流中的最小流量 = 当前流量 - 残量网络(去掉该边双向弧)中 a->b 可改道的最大流
        reroute = Dinic(N)
        for u, v, c in arcs:
            if (u, v) == (a, b) or (u, v) == (b, a):
                continue
            reroute.add(u, v, c)
        q = f_e - reroute.maxflow(a, b)
        if q > 0:
            confirmed[(i, j)] = q
    got = [0] * n
    for (i, j), q in confirmed.items():
        got[i] += q
    pending = {i: orders[i]['required'] - got[i] for i in range(n)}
    return {'feasible': True, 'confirmed': confirmed, 'pending': pending}
