import {loadAll} from '../api/business.js';
export const genKey=()=>globalThis.crypto?.randomUUID?crypto.randomUUID():'batch-'+Date.now()+'-'+Math.random().toString(36).slice(2,10);
export const store={session:JSON.parse(localStorage.getItem('session')||'null'),data:{sources:[],periods:[],policies:[],runs:[],schedules:[],deliveries:[],audits:[],reconBatches:[]},selected:null,recon:{run_id:null,pool:null,orders:[],batchKey:genKey(),result:null,batch:null}};
export async function reload(){store.data=await loadAll()}
export function setSession(value){store.session=value;if(value)localStorage.setItem('session',JSON.stringify(value));else localStorage.removeItem('session')}
