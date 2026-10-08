import {Capacitor} from '@capacitor/core';
import {LocalNotifications} from '@capacitor/local-notifications';
export async function permission() {
  if(!Capacitor.isNativePlatform()) throw Error('Phone reminders are available in the Android app.');
  const result=await LocalNotifications.requestPermissions();
  if(result.display!=='granted')throw Error('Notifications were not allowed. Enable them in Android settings.');
}
export async function reminders(items,enabled) {
  if(!Capacitor.isNativePlatform())return;
  const pending=await LocalNotifications.getPending();
  if(pending.notifications.length)await LocalNotifications.cancel({notifications:pending.notifications.map(n=>({id:n.id}))});
  if(!enabled)return;
  if((await LocalNotifications.checkPermissions()).display!=='granted')return;
  const due=items.filter(x=>x.kind==='deadline'&&!x.deleted&&!x.completed)
    .map(x=>({...x,at:new Date(x.due+'T09:00:00')})).filter(x=>x.at>Date.now())
    .sort((a,b)=>a.at-b.at).slice(0,100);
  if(due.length)await LocalNotifications.schedule({notifications:due.map((x,i)=>({id:i+1,title:'DeadlineHub reminder',body:x.title,schedule:{at:x.at},extra:{itemId:x.id}}))});
}
