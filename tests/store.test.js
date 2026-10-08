import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mergeRows} from '../src/store.js';
test('acknowledged edit becomes clean',()=>{const sent=[{id:'a',op:'1',dirty:true,title:'First'}];assert.deepEqual(mergeRows(sent,[{id:'a',rev:2,title:'First'}],sent),[{id:'a',rev:2,title:'First',dirty:false}]);});
test('editing during sync preserves new local work and updates base revision',()=>{const current=[{id:'a',op:'2',dirty:true,title:'Second'}];const result=mergeRows(current,[{id:'a',rev:2,title:'First'}],[{id:'a',op:'1',rev:1,title:'First'}]);assert.equal(result[0].title,'Second');assert.equal(result[0].dirty,true);assert.equal(result[0].rev,2);});
test('remote tombstones and conflict copies are retained',()=>{const result=mergeRows([{id:'a',dirty:false}], [{id:'a',rev:2,deleted:true},{id:'b',title:'Copy',rev:1}],[]);assert.equal(result[0].deleted,true);assert.equal(result[1].title,'Copy');});

test('unrelated remote edit does not erase conflict detection for a new local edit',()=>{const result=mergeRows([{id:'a',op:'new',rev:1,dirty:true,title:'My edit'}],[{id:'a',rev:2,title:'Their edit'}],[]);assert.equal(result[0].rev,1);assert.equal(result[0].title,'My edit');});
