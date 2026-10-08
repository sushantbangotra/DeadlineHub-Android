let db;
export async function openDB() {
  db = await new Promise((resolve,reject)=>{
    const r=indexedDB.open('deadlinehub-mobile-v1',1);
    r.onupgradeneeded=()=>r.result.createObjectStore('items',{keyPath:'key'});
    r.onsuccess=()=>resolve(r.result); r.onerror=()=>reject(r.error);
  });
}
const key=(scope,id)=>JSON.stringify([scope,id]);
export async function all(scope) {
  return new Promise((resolve,reject)=>{
    const r=db.transaction('items').objectStore('items').getAll();
    r.onsuccess=()=>resolve(r.result.filter(x=>x.scope===scope));r.onerror=()=>reject(r.error);
  });
}
export function mergeRows(current, remote, sent) {
  const byId=new Map(current.map(x=>[x.id,x]));
  for(const row of remote){
    const old=byId.get(row.id);
    if(old?.dirty && !sent.some(s=>s.id===old.id && s.op===old.op)) {
      // Only rebase onto our own acknowledged write. A competing remote write must conflict.
      const prior=sent.find(s=>s.id===old.id);
      const fields=['id','kind','title','deleted','updated','due','category','priority','completed','content','pinned'];
      const acknowledged=prior && row.rev===prior.rev+1 && fields.every(k=>row[k]===prior[k]);
      byId.set(row.id,{...old,rev:acknowledged?row.rev:old.rev});
    } else byId.set(row.id,{...row,dirty:false});
  }
  return [...byId.values()];
}
export async function save(scope,item) {
  const row={...item,scope,key:key(scope,item.id),dirty:true,op:crypto.randomUUID()};
  await transact(store=>store.put(row)); return row;
}
function transact(fn) {
  return new Promise((resolve,reject)=>{
    const tx=db.transaction('items','readwrite');fn(tx.objectStore('items'));
    tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
  });
}
export function applyRemote(scope,remote,sent) {
  return transact(store=>{
    const req=store.getAll();req.onsuccess=()=>{
      for(const row of mergeRows(req.result.filter(x=>x.scope===scope),remote,sent))
        store.put({...row,scope,key:key(scope,row.id)});
    };
  });
}
export async function importGuest(scope) {
  const guest=(await all('guest')).filter(x=>!x.deleted);
  await transact(store=>{
    for(const x of guest){const id=crypto.randomUUID();store.put({...x,id,scope,key:key(scope,id),rev:0,dirty:true,op:crypto.randomUUID()});}
  });return guest.length;
}
