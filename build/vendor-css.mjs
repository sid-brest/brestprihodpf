import fs from 'node:fs';
const rd = p => fs.readFileSync(p, 'utf8').replace(/\r\n/g, '\n');
let bs = rd('css/vendor/bootstrap.min.css');
const before = bs.length;
bs = bs.replace(/@font-face\{font-family:'Glyphicons Halflings'[^}]*\}/, '');
bs = bs.replace(/\.glyphicon(?:-[a-z0-9-]+)?(?::before)?(?:,\.glyphicon[^{]*)?\{[^}]*\}/g, '');
console.log('bootstrap', before, '->', bs.length);
const an = rd('css/vendor/animate.css');
const block = (start) => {
  const i = an.indexOf(start); if (i < 0) throw new Error('missing ' + start);
  const j = an.indexOf('\n}\n', i); return an.slice(i, j + 3);
};
let anOut = '/*! animate.css subset (fadeIn, fadeInUp, fadeInLeft, fadeInRight) | MIT | https://animate.style */\n';
for (const n of ['fadeIn', 'fadeInUp', 'fadeInLeft', 'fadeInRight']) {
  anOut += block(`@-webkit-keyframes ${n} {`) + block(`@keyframes ${n} {`) + block(`\n.${n} {`).trimStart() + '\n';
}
console.log('animate', an.length, '->', anOut.length);
let fx = rd('css/vendor/flexslider.css');
fx = fx.replace(/@font-face\s*\{[^}]*flexslider-icon[^}]*\}/, '');
console.log('flexslider', fx.length, 'font-face left', (fx.match(/@font-face/g) || []).length);
const extra = '.probootstrap-animated{-webkit-animation-duration:.8s;animation-duration:.8s;-webkit-animation-fill-mode:both;animation-fill-mode:both}\n';
fs.writeFileSync(process.argv[2], bs + '\n' + anOut + '\n' + fx + '\n' + extra);
