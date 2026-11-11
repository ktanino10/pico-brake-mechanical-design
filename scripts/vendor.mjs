import {readFile, writeFile, copyFile, mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';

const root = new URL('../', import.meta.url);
const packageRoot = new URL('node_modules/three/', root);
const metadata = JSON.parse(await readFile(new URL('package.json', packageRoot), 'utf8'));
if (metadata.version !== '0.186.1') throw new Error('Unexpected three.js version');
await mkdir(new URL('vendor/', root), {recursive: true});
const sources = {
  'three.module.js': 'build/three.module.js',
  'three.core.js': 'build/three.core.js',
  'OrbitControls.js': 'examples/jsm/controls/OrbitControls.js',
  'THREE-LICENSE.txt': 'LICENSE',
};
const files = [];
for (const [target, source] of Object.entries(sources)) {
  const destination = new URL(`vendor/${target}`, root);
  await copyFile(new URL(source, packageRoot), destination);
  files.push({path: `vendor/${target}`, sha256: createHash('sha256').update(await readFile(destination)).digest('hex')});
}
await writeFile(new URL('vendor/manifest.json', root), `${JSON.stringify({
  package: 'three', version: metadata.version, license: 'MIT',
  upstream: 'https://github.com/mrdoob/three.js', modified: false, files,
}, null, 2)}\n`);
console.log(`Vendored three.js ${metadata.version}; ${files.length} exact licensed files.`);
