const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const a = src.indexOf('const esc'), b = src.indexOf('\n', a);
const m1 = src.indexOf('function md('), m2 = src.indexOf('// YouTube/Vimeo');
eval(src.slice(a, b) + '\n' + src.slice(m1, m2) + '\nglobalThis.md = md;');
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
console.log(JSON.stringify(cases.map(c => md(c))));
