#!/usr/bin/env node
/**
 * Verifies that the production build excludes test instrumentation code.
 * This script runs after `vite build` to ensure tree-shaking is working correctly.
 */

const fs = require('fs');
const path = require('path');

const DIST_DIR = path.join(__dirname, '../dist/assets');
const FORBIDDEN_PATTERNS = [
  'emitTestEvent',
  'window.__playwright_emitTestEvent',
  'VITE_TEST_MODE',
  'isTestMode',
];

function searchInFile(filePath, patterns) {
  const content = fs.readFileSync(filePath, 'utf8');
  const found = [];

  for (const pattern of patterns) {
    if (content.includes(pattern)) {
      found.push(pattern);
    }
  }

  return found;
}

function verifyBuild() {
  if (!fs.existsSync(DIST_DIR)) {
    console.error('Error: dist/assets directory not found. Run `pnpm build` first.');
    process.exit(1);
  }

  const files = fs.readdirSync(DIST_DIR).filter(f => f.endsWith('.js'));
  const violations = [];

  for (const file of files) {
    const filePath = path.join(DIST_DIR, file);
    const found = searchInFile(filePath, FORBIDDEN_PATTERNS);

    if (found.length > 0) {
      violations.push({ file, patterns: found });
    }
  }

  if (violations.length > 0) {
    console.error('❌ Build verification failed: Test instrumentation code found in production build\n');
    for (const { file, patterns } of violations) {
      console.error(`  ${file}:`);
      for (const pattern of patterns) {
        console.error(`    - ${pattern}`);
      }
    }
    console.error('\nEnsure VITE_TEST_MODE is set to "false" in production builds.');
    process.exit(1);
  }

  console.log('✅ Build verification passed: No test instrumentation code in production build');
}

verifyBuild();
