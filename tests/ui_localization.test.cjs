const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('every declared UI translation has an English catalog entry', () => {
    const source=fs.readFileSync('src/templates/ui.js','utf8');
    const context={matchMedia:()=>({matches:false,addEventListener(){}})};vm.createContext(context);
    vm.runInContext(source.slice(0,source.indexOf('function showStatus'))+';globalThis.catalog=UI_EN;',context);
    const html=fs.readFileSync('src/templates/plcn.html','utf8');
    const decode=value=>value.replaceAll('&quot;','"').replaceAll('&#x27;',"'").replaceAll('&lt;','<').replaceAll('&gt;','>').replaceAll('&amp;','&');
    const labels=[...html.matchAll(/data-i18n(?:-(?:placeholder|title|aria-label))?="([^"]+)"/g)].map(match=>decode(match[1]));
    for(const label of labels){assert.ok(context.catalog[label],`Missing English text: ${label}`);assert.doesNotMatch(context.catalog[label],/\p{Script=Han}/u,`English entry contains Chinese: ${label}`);}
});


test('English count labels use singular forms for one game, list or item',()=>{
 const source=fs.readFileSync('src/templates/ui.js','utf8');const context={matchMedia:()=>({matches:false,addEventListener(){}})};vm.createContext(context);
 vm.runInContext(source+";currentUILanguage='en';",context);
 assert.equal(context.formatGameCount(1),'1 game');assert.equal(context.formatGameCount(2),'2 games');
 assert.equal(context.formatGameListCount(1),'1 game list');assert.equal(context.formatItemCount(1),'1 item');
});
