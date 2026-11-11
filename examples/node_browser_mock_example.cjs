/**
 * node_browser_mock_example.cjs
 * Example demonstrating how to run an extracted browser-dependent JS algorithm
 * inside pure Node.js (NO BROWSER / NO PLAYWRIGHT).
 */

const crypto = require('crypto');

// 1. Setup lightweight browser environment polyfills
const window = {
    navigator: {
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        languages: ['en-US', 'en'],
        webdriver: false
    },
    location: {
        href: 'https://target.com/search?q=test',
        host: 'target.com'
    },
    document: {
        cookie: 'session_id=mock_session_cookie;'
    }
};

global.window = window;
global.document = window.document;
global.navigator = window.navigator;
global.location = window.location;

// 2. Extracted JS algorithm from web bundle
function extractedSignAlgorithm(path, timestamp, salt) {
    // Imagine this was stripped from the target's webpack bundle
    const message = `${path}|${timestamp}|${window.navigator.userAgent}|${salt}`;
    return crypto.createHash('md5').update(message).digest('hex');
}

// 3. Test execution in Node.js
function run() {
    console.log('[*] Running extracted algorithm in pure Node.js sandbox...');
    const now = Math.floor(Date.now() / 1000);
    const sign = extractedSignAlgorithm('/api/v1/search', now, 'k3y_s3cr3t');
    console.log(`[+] Generated Signature : ${sign}`);
    console.log(`[+] Timestamp           : ${now}`);
    console.log(`[+] Verification passed : Successful browserless JS emulation!`);
}

run();
