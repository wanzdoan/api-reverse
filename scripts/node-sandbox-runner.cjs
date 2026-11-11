#!/usr/bin/env node
/**
 * node-sandbox-runner.cjs - Pure Node.js Browser Emulation Harness (NO REAL BROWSER)
 *
 * Used for "Bổ JS" (Running extracted client-side JS algorithms in Node.js).
 * Provides lightweight polyfills for window, document, navigator, location, crypto,
 * neutralizes anti-debugging checks, and executes the target algorithm.
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

function printUsage() {
    console.log(`
Usage:
  node node-sandbox-runner.cjs <extracted_code.js> [options]

Options:
  --call <function_name>     Name of the function to execute (e.g., getSign, encryptPayload)
  --args '<json_array>'      JSON array of arguments to pass to the function (e.g., '["/api/data", 1727000000]')
  --url <target_url>         Mock URL for location/document (default: https://target.com/)
  --ua <user_agent>          Mock User-Agent string
  --serve <port>             Run as a lightweight local HTTP RPC service for Python integration
  --help, -h                 Show this help message
`);
}

function createBrowserSandbox(options = {}) {
    const targetUrl = options.url || 'https://target.com/';
    const parsedUrl = new URL(targetUrl);
    const userAgent = options.ua || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

    const storageMap = new Map();
    const mockStorage = {
        getItem: (k) => storageMap.get(k) || null,
        setItem: (k, v) => storageMap.set(k, String(v)),
        removeItem: (k) => storageMap.delete(k),
        clear: () => storageMap.clear(),
        length: 0
    };

    const mockDocument = {
        cookie: '',
        referrer: '',
        title: 'Target Site',
        createElement: (tag) => {
            if (tag.toLowerCase() === 'canvas') {
                return {
                    getContext: () => ({
                        fillText: () => {},
                        getImageData: () => ({ data: new Uint8Array(16) })
                    }),
                    toDataURL: () => 'data:image/png;base64,mock'
                };
            }
            return {
                style: {},
                setAttribute: () => {},
                appendChild: () => {}
            };
        },
        getElementById: () => null,
        getElementsByTagName: () => [],
        head: {},
        body: {}
    };

    const mockNavigator = {
        userAgent: userAgent,
        appVersion: userAgent.replace('Mozilla/', ''),
        platform: 'Win32',
        language: 'en-US',
        languages: ['en-US', 'en'],
        webdriver: false,
        plugins: [{ name: 'Chrome PDF Plugin' }],
        hardwareConcurrency: 8,
        cookieEnabled: true
    };

    const mockLocation = {
        href: targetUrl,
        protocol: parsedUrl.protocol,
        host: parsedUrl.host,
        hostname: parsedUrl.hostname,
        port: parsedUrl.port,
        pathname: parsedUrl.pathname,
        search: parsedUrl.search,
        hash: parsedUrl.hash,
        origin: parsedUrl.origin
    };

    const sandbox = {
        console: console,
        setTimeout: setTimeout,
        clearTimeout: clearTimeout,
        setInterval: setInterval,
        clearInterval: clearInterval,
        Buffer: Buffer,
        btoa: (str) => Buffer.from(str, 'binary').toString('base64'),
        atob: (b64) => Buffer.from(b64, 'base64').toString('binary'),
        Date: Date,
        Math: Math,
        JSON: JSON,
        RegExp: RegExp,
        Array: Array,
        Object: Object,
        String: String,
        Number: Number,
        Boolean: Boolean,
        crypto: {
            getRandomValues: (buf) => require('crypto').randomFillSync(buf),
            subtle: {}
        }
    };

    // Circular references matching browser window
    sandbox.window = sandbox;
    sandbox.self = sandbox;
    sandbox.top = sandbox;
    sandbox.parent = sandbox;
    sandbox.global = sandbox;
    sandbox.globalThis = sandbox;

    sandbox.document = mockDocument;
    sandbox.navigator = mockNavigator;
    sandbox.location = mockLocation;
    sandbox.localStorage = mockStorage;
    sandbox.sessionStorage = mockStorage;

    return sandbox;
}

function neutralizeAntiDebug(code) {
    // Suppress infinite debugger; in Function and eval
    return code
        .replace(/debugger\s*;?/g, '/* debugger neutralized */')
        .replace(/function\s*\(\s*\)\s*\{\s*return\s+this;?\s*\}\(\s*\)/g, 'window');
}

function main() {
    const args = process.argv.slice(2);
    if (args.length === 0 || args.includes('-h') || args.includes('--help')) {
        printUsage();
        process.exit(0);
    }

    const scriptPath = args[0];
    if (!fs.existsSync(scriptPath)) {
        console.error(`[-] File not found: ${scriptPath}`);
        process.exit(1);
    }

    let targetFunc = null;
    let funcArgs = [];
    let targetUrl = 'https://target.com/';
    let rpcPort = null;

    for (let i = 1; i < args.length; i++) {
        if (args[i] === '--call') {
            targetFunc = args[++i];
        } else if (args[i] === '--args') {
            try {
                funcArgs = JSON.parse(args[++i]);
            } catch (e) {
                console.error(`[-] Error parsing --args JSON: ${e.message}`);
                process.exit(1);
            }
        } else if (args[i] === '--url') {
            targetUrl = args[++i];
        } else if (args[i] === '--serve') {
            rpcPort = parseInt(args[++i], 10);
        }
    }

    console.log(`[*] Pure Node.js Emulation Mode (NO BROWSER)`);
    console.log(`[*] Loading script: ${scriptPath}`);
    let rawCode = fs.readFileSync(scriptPath, 'utf-8');
    rawCode = neutralizeAntiDebug(rawCode);

    const sandbox = createBrowserSandbox({ url: targetUrl });
    const context = vm.createContext(sandbox);

    try {
        console.log(`[*] Executing script in sandboxed context...`);
        const script = new vm.Script(rawCode, { filename: path.basename(scriptPath) });
        script.runInContext(context, { timeout: 5000 });
        console.log(`[+] Script context initialized successfully!`);
    } catch (e) {
        console.error(`[-] Error executing script context: ${e.stack}`);
        process.exit(1);
    }

    // If running in local RPC service mode
    if (rpcPort) {
        const http = require('http');
        const server = http.createServer((req, res) => {
            if (req.method === 'POST') {
                let body = '';
                req.on('data', chunk => { body += chunk; });
                req.on('end', () => {
                    try {
                        const payload = JSON.parse(body || '{}');
                        const fnName = payload.function || targetFunc;
                        const callArgs = payload.args || [];
                        
                        if (!fnName || typeof context[fnName] !== 'function') {
                            res.writeHead(400, { 'Content-Type': 'application/json' });
                            return res.end(JSON.stringify({ error: `Function '${fnName}' not found in context` }));
                        }

                        const result = context[fnName](...callArgs);
                        res.writeHead(200, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify({ success: true, result }));
                    } catch (err) {
                        res.writeHead(500, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify({ success: false, error: err.message }));
                    }
                });
            } else {
                res.writeHead(200, { 'Content-Type': 'text/plain' });
                res.end(`Node Sandbox RPC Server Active. Call function '${targetFunc || '<name>'}' via POST JSON.`);
            }
        });

        server.listen(rpcPort, '127.0.0.1', () => {
            console.log(`\n[+] Local Node RPC Server listening on http://127.0.0.1:${rpcPort}`);
            console.log(`    Python can invoke functions via: requests.post('http://127.0.0.1:${rpcPort}', json={'function': '${targetFunc || 'test'}', 'args': [...]})`);
        });
        return;
    }

    // Direct CLI execution
    if (targetFunc) {
        if (typeof context[targetFunc] !== 'function') {
            console.error(`[-] Function '${targetFunc}' does not exist in context or is not exported globally.`);
            console.log(`[*] Available global keys:`, Object.keys(context).filter(k => !['window', 'document', 'navigator', 'location', 'console'].includes(k)).slice(0, 20));
            process.exit(1);
        }

        console.log(`[*] Calling: ${targetFunc}(${funcArgs.map(a => JSON.stringify(a)).join(', ')})`);
        const startTime = process.hrtime.bigint();
        const result = context[targetFunc](...funcArgs);
        const endTime = process.hrtime.bigint();
        const durationMs = Number(endTime - startTime) / 1e6;

        console.log(`\n[+] EXECUTION RESULT:`);
        console.log(JSON.stringify(result, null, 2));
        console.log(`[*] Execution time: ${durationMs.toFixed(3)} ms`);
    } else {
        console.log(`[*] Script ran without error. Use --call <func> to invoke specific functions.`);
    }
}

main();
