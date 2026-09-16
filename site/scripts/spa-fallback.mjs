// GitHub Pages serves 404.html for unknown paths; copying index.html there lets the
// React router handle deep links such as /league/PD.
import { copyFileSync } from 'node:fs'
copyFileSync('dist/index.html', 'dist/404.html')
console.log('Wrote dist/404.html for SPA routing')
