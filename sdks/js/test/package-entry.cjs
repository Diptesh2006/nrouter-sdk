'use strict';

const assert = require('node:assert/strict');
const sdk = require('../dist/index.js');

assert.equal(typeof sdk.nRouter, 'function');
assert.equal(sdk.default, sdk.nRouter);
console.log('CommonJS package entry: PASS');
