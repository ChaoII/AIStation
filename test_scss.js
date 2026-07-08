const sass = require('sass');
const path = require('path');
const fs = require('fs');

// Test 1: Simple SCSS with nesting
try {
  const result = sass.compileString('.test { &:hover { color: red; } .nested { &::before { content: "x"; } } }');
  console.log('Test 1 (simple nesting): OK');
} catch (e) {
  console.log('Test 1 FAILED:', e.message);
}

// Test 2: With @use
try {
  const varsPath = path.join(__dirname, 'frontend/src/styles/variables.scss');
  const result = sass.compileString('@use "' + varsPath.replace(/\\/g, '/') + '" as *; .test { &:hover { color: red; } }');
  console.log('Test 2 (with @use variables): OK');
} catch (e) {
  console.log('Test 2 FAILED:', e.message.substring(0, 200));
}

// Test 3: Check non-scoped style block behavior
try {
  const result = sass.compileString('.a { color: red; } .b { color: blue; &:hover { color: green; } } .c { height: 500px; }');
  console.log('Test 3 (multi-rule with nesting): OK');
  if (result.css.includes('height: 500px')) {
    console.log('  - .c height preserved: YES');
  } else {
    console.log('  - .c height preserved: NO');
  }
} catch (e) {
  console.log('Test 3 FAILED:', e.message);
}
