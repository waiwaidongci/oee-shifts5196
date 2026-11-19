import {heading} from '../components/common/header.js';import {table} from '../components/common/table.js';import {esc,time} from '../utils/format.js';import {store} from '../stores/business.js';
export const defaultOrder=pool=>{const s=pool?.shifts?.[0];return {order_no:'PO-'+Math.random().toString(36).slice(2,8).toUpperCase(),device:s?.device||'',day:s?.day||new Date().toISOString().slice(0,10),start:s?.start??480,end:s?.end??1020,required:100}};
const shiftText=s=>`${esc(s.day)} ${esc(s.device)} ${s.start}–${s.end}分`;
function poolView(pool){
 if(!pool)return '<p class="empty">选择一份已复核报告后显示班次良品余量。</p>';
 return `<h3>班次良品余量 · 报告「${esc(pool.name)}」（原报告保留，占用另记对账表）</h3>`+table(pool.shifts.map(s=>({班次:'#'+s.key,日期:s.day,设备:s.device,开始分钟:s.start,结束分钟:s.end,良品:s.good,已确认:s.confirmed,剩余:s.remaining})));
}
function entryView(recon,pool){
 const devices=[...new Set((pool?.shifts||[]).map(s=>s.device))];
 const rows=recon.orders.map((o,i)=>`<div class="policy-row"><label>工单号<input data-k="order_no" data-i="${i}" value="${esc(o.order_no)}" required></label><label>设备<input data-k="device" data-i="${i}" list="recon-devices" value="${esc(o.device)}" required></label><label>日期<input data-k="day" data-i="${i}" type="date" value="${esc(o.day)}" required></label><label>开始分钟<input data-k="start" data-i="${i}" type="number" min="0" max="2879" value="${o.start}" required></label><label>结束分钟<input data-k="end" data-i="${i}" type="number" min="1" max="2880" value="${o.end}" required></label><label>良品需求<input data-k="required" data-i="${i}" type="number" min="1" value="${o.required}" required></label><button type="button" class="remove-order" data-i="${i}">删除工单</button></div>`).join('');
 return `<details open><summary>录入外部厂商工单（同设备、时段相交才参与分配，整数良品）</summary><datalist id="recon-devices">${devices.map(d=>`<option value="${esc(d)}">`).join('')}</datalist><div id="order-rows">${rows}</div><p><button type="button" id="add-order">增加工单</button></p><p>批次键 <code>${esc(recon.batchKey)}</code>（同批重试不重复占用；确认成功后自动更换）</p><button type="button" id="recon-preview">试算分配</button> <button type="button" id="recon-confirm">确认占用</button><p>确认时按最新剩余良品重算整批；若余量已被其他确认占用，以新余量结果为准。无解则整批不占量。</p></details>`;
}
function resultView(r){
 if(!r)return '';
 if(!r.feasible)return `<section class="report"><div class="report-top"><h2>整批无解，未占用任何良品</h2></div><p class="error">缺口合计 ${r.shortage} 件。以下工单与班次卡住，请调整需求或等余量变化后整批重试。</p><h3>卡住的工单</h3>${table(r.stuck_orders.map(o=>({工单号:o.order_no,设备:o.device,日期:o.day,开始分钟:o.start,结束分钟:o.end,需求:o.required,本次缺口:o.unmet})))}<h3>卡住的班次（剩余已被占满）</h3>${r.stuck_shifts.length?table(r.stuck_shifts.map(s=>({班次:'#'+s.shift_key,日期:s.day,设备:s.device,开始分钟:s.start,结束分钟:s.end,剩余良品:s.remaining}))):'<p class="empty">卡住工单在同设备下没有相交班次。</p>'}</section>`;
 const summary=r.orders.map(o=>({工单号:o.order_no,设备:o.device,日期:o.day,开始分钟:o.start,结束分钟:o.end,需求:o.required,已确认:o.confirmed,待核:o.pending}));
 const allocs=[];for(const o of r.orders)for(const a of o.allocations)allocs.push({工单号:o.order_no,归属班次:shiftText(a),确认数:a.qty});
 return `<section class="report"><div class="report-top"><h2>${r.id?`已确认占用 · 批次 #${r.id}`:'试算结果（未占用）'}</h2></div><div class="metrics"><div><small>需求合计</small><strong>${r.required}</strong></div><div><small>确认合计</small><strong>${r.confirmed}</strong></div><div><small>待核合计</small><strong>${r.pending}</strong></div></div>${r.pending?'<p class="warning">存在多种分法：每对工单和班次仅确认各种分法共有的数量，余量待核。</p>':'<p>分法唯一，需求全部确认到班次。</p>'}<h3>工单归属与待核量</h3>${table(summary)}<h3>确认归属明细</h3>${table(allocs)}</section>`;
}
function batchesView(d,recon){
 const rows=d.reconBatches.map(b=>{const run=d.runs.find(r=>r.id===b.run_id);return `<tr><td>#${b.id}</td><td>${esc(b.batch_key)}</td><td>${esc(run?.name||b.run_id)}</td><td>${b.required}</td><td>${b.confirmed}</td><td>${b.pending}</td><td>${esc(b.actor)}</td><td>${time(b.created)}</td><td><button class="recon-batch" data-id="${b.id}">查归属</button></td></tr>`}).join('');
 return `<h3>已确认批次</h3>${rows.length?`<div class="table-wrap"><table><thead><tr><th>批次</th><th>批次键</th><th>对账报告</th><th>需求</th><th>确认</th><th>待核</th><th>操作人</th><th>时间</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`:'<p class="empty">尚无对账批次。</p>'}${recon.batch?`<h3>批次 #${recon.batch.id} 归属与待核</h3>`+resultView(recon.batch):''}`;
}
export function reconcile(c,d){
 const recon=store.recon,approved=d.runs.filter(r=>r.status==='completed'&&r.approved);
 if(!recon.run_id||!approved.some(r=>r.id===recon.run_id))recon.run_id=approved[0]?.id||null;
 if(!recon.orders.length)recon.orders=[defaultOrder(recon.pool)];
 const picker=approved.length?`<label>对账报告（仅已复核）<select id="recon-run">${approved.map(r=>`<option value="${r.id}" ${r.id===recon.run_id?'selected':''}>${esc(r.name)}</option>`).join('')}</select></label>`:'<p class="empty">暂无已复核报告，请先在「核算与复核」完成复核。</p>';
 return heading('RECONCILE DESK / 06','厂商工单跨班对账','外部工单按同设备、时段相交分配整数良品；多种分法仅确认共有数量，余量待核；无解整批不占量。')+picker+poolView(recon.pool)+(approved.length?entryView(recon,recon.pool):'')+resultView(recon.result)+batchesView(d,recon);
}
