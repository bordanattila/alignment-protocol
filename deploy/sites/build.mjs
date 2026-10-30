// Embed only the existing Vite assets in a Worker ESM artifact. No backend data.
import { readFile, writeFile, mkdir, readdir, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, join, extname } from 'node:path';
import { spawnSync } from 'node:child_process';

const root = fileURLToPath(new URL('.', import.meta.url));
const repository = resolve(root, '../..');
const frontend = join(repository, 'frontend');
const local = process.argv.slice(2).includes('--local');
if (process.argv.slice(2).some(arg => arg !== '--local')) throw new Error('Only --local is supported.');
// Local verification creates no fake Site identity or deployable manifest.
const manifest = local ? null : JSON.parse(await readFile(join(repository, '.openai/hosting.json'), 'utf8'));
if (!local && (typeof manifest.project_id !== 'string' || !manifest.project_id.trim() || manifest.static)) {
  throw new Error('Register an owner-private Site after approval, then set its real project_id; this is a Worker build.');
}
const build = spawnSync('npm', ['run', 'build'], { cwd: frontend, stdio: 'inherit' });
if (build.status !== 0) process.exit(build.status ?? 1);
const assets = {};
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };
async function collect(directory, prefix = '') {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const relative = `${prefix}/${entry.name}`;
    if (entry.isDirectory()) await collect(join(directory, entry.name), relative);
    else {
      const type = types[extname(entry.name)];
      if (!type) throw new Error(`Review unexpected frontend asset type: ${relative}`);
      assets[relative] = { body: (await readFile(join(directory, entry.name))).toString('base64'), type };
    }
  }
}
await collect(join(frontend, 'dist'));
assets['/'] = assets['/index.html'];
const output = join(repository, 'dist');
await rm(output, { recursive: true, force: true });
await mkdir(join(output, 'server'), { recursive: true });
await mkdir(join(output, '.openai'), { recursive: true });
await writeFile(join(output, 'server/index.js'), `${await readFile(join(root, 'worker.mjs'), 'utf8')}\nexport default createWorker(${JSON.stringify(assets)});\n`);
if (manifest) await writeFile(join(output, '.openai/hosting.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log('Built existing React frontend and server-only relay. No deployment performed.');
