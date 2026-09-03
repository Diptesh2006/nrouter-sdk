import assert from 'node:assert/strict';
import DefaultRouter, { nRouter as NamedRouter } from '../dist/index.mjs';

assert.equal(typeof DefaultRouter, 'function');
assert.equal(typeof NamedRouter, 'function');
assert.equal(DefaultRouter, NamedRouter);
console.log('ESM package entry: PASS');
