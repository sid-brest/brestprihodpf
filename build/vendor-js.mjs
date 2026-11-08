// Concatenates the vendor scripts the page actually uses (order matters). Output is minified by terser (see package.json).
import fs from 'node:fs';
const files = [
  'js/vendor/jquery.min.js',          // jQuery 1.12.4
  'js/vendor/jquery.easing.1.3.js',   // easeInOutExpo for the menu scroll
  'js/vendor/jquery.stellar.min.js',  // parallax backgrounds (desktop only)
  'js/vendor/jquery.flexslider-min.js',
  'js/vendor/bootstrap.min.js',       // navbar collapse + modal
  'js/vendor/jquery.waypoints.min.js' // scroll animations + active menu item
];
fs.writeFileSync(process.argv[2], files.map(f => fs.readFileSync(f, 'utf8')).join('\n;\n'));
console.log('concatenated', files.length, 'files');
