// Use the existing Vite/esbuild toolchain and Node runner; no test dependencies.
import { build } from 'esbuild';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const directory = await mkdtemp(join(tmpdir(), 'consensus-ui-'));
try {
  const result = await build({
    entryPoints: ['gameplay.test.tsx', 'missionConnection.test.ts'].map(file => new URL(file, import.meta.url).pathname),
    outdir: directory,
    bundle: true, platform: 'node', format: 'cjs', jsx: 'automatic', write: false,
    banner: { js: 'globalThis.location = { search: "", href: "http://localhost/?mission=test" };' },
    plugins: [{
      name: 'authoritative-state-fixture',
      setup(builder) {
        // Exercise the real App and gameplay markup while supplying deterministic
        // server snapshots. Socket protocol is tested by the backend suite.
        builder.onResolve({ filter: /^\.\/(useLobby|session)$/ }, args => ({ path: args.path, namespace: 'fixture' }));
        builder.onLoad({ filter: /.*/, namespace: 'fixture' }, args => ({
          contents: args.path === './useLobby'
            ? 'export function useLobby() { return globalThis.__testLobby; }'
            : 'export function restoreSession() { return { token: "test", credential: "private" }; } export function clearSession() {} export function saveSession() {}',
          loader: 'js',
        }));
      },
    }],
  });
  for (const output of result.outputFiles) await writeFile(output.path.replace(/\.js$/, '.cjs'), output.contents);
  const execution = spawnSync(process.execPath, ['--test', join(directory, 'gameplay.test.cjs'), join(directory, 'missionConnection.test.cjs')], { stdio: 'inherit' });
  process.exitCode = execution.status ?? 1;
} finally {
  await rm(directory, { recursive: true, force: true });
}
