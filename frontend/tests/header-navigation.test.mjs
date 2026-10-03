import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const source = await readFile(new URL('../lib/cms.ts', import.meta.url), 'utf8');
async function navigationFor(navigation, location) {
  const exports = {};
  const sandbox = {
    exports,
    process: { env: { CMS_API_URL: 'https://cms.example.test/api/v1' } },
    AbortSignal,
    URL,
    fetch: async () => ({ ok: true, json: async () => ({ navigation }) }),
    require: (name) => name === 'react' ? { cache: (fn) => fn } : {},
  };
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, sandbox);
  return Array.from(await exports.getManagedNavigation(location), (item) => ({ ...item }));
}
const required = ['/courses', '/how-it-works', '/pricing', '/about', '/book-online-live-class', '/contact'];

test('booking-only CMS navigation keeps every public page in the header', async () => {
  const items = await navigationFor([{ label: 'Book online live class', url: '/book-online-live-class', location: 'both', order: 1, open_in_new_tab: false }], 'header');
  assert.deepEqual(items.map((item) => item.url), required);
});
test('About remains in the header when CMS assigns it only to the footer', async () => {
  const items = await navigationFor([{ label: 'About', url: '/about', location: 'footer', order: 99, open_in_new_tab: false }], 'header');
  assert.equal(items.filter((item) => item.url === '/about').length, 1);
});
test('empty CMS and custom navigation preserve public links without duplicates', async () => {
  assert.deepEqual((await navigationFor([], 'header')).map((item) => item.url), required);
  const items = await navigationFor([{ label: 'Resources', url: '/resources', location: 'header', order: 60, open_in_new_tab: false }], 'header');
  assert.deepEqual(items.map((item) => item.url), [...required, '/resources']);
});
