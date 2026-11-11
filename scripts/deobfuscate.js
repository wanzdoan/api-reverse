#!/usr/bin/env node
/**
 * deobfuscate.cjs - AST & Pattern-based JavaScript Deobfuscator
 *
 * Capabilities:
 * 1. String array extraction & decoder function evaluation (Obfuscator.io / JS-Obfuscator)
 * 2. Hex / Unicode escape sequence decoding (\x61, \u0041)
 * 3. Constant folding (!0 -> true, !1 -> false, 0x1a -> 26)
 * 4. Member expression simplification (obj['prop'] -> obj.prop)
 * 5. Webpack bundle / chunk unpacker (splits modules into readable files)
 * 6. Optional delegation to webcrack (`--engine webcrack`)
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { execSync } = require('child_process');

function printUsage() {
    console.log(`
Usage:
  node deobfuscate.cjs <input_file.js> [options]

Options:
  --out, -o <file|dir>     Output file path or directory (default: <name>.deobf.js)
  --unpack-webpack         Attempt to unpack Webpack chunk/bundle into separate modules
  --engine webcrack        Use npx webcrack for deep AST unflattening and deobfuscation
  --help, -h               Show this help message
`);
}

function decodeEscapeSequences(code) {
    // Decode \xHH escapes in strings
    return code.replace(/\\x([0-9a-fA-F]{2})/g, (match, hex) => {
        const char = String.fromCharCode(parseInt(hex, 16));
        // Avoid unescaping quotes that break string delimiters
        if (char === '"' || char === "'" || char === '\\' || char === '\n' || char === '\r') {
            return match;
        }
        return char;
    }).replace(/\\u([0-9a-fA-F]{4})/g, (match, hex) => {
        const char = String.fromCharCode(parseInt(hex, 16));
        if (char === '"' || char === "'" || char === '\\' || char === '\n' || char === '\r') {
            return match;
        }
        return char;
    });
}

function simplifyConstants(code) {
    let result = code;
    // !0 -> true, !1 -> false
    result = result.replace(/!0\b/g, 'true');
    result = result.replace(/!1\b/g, 'false');
    result = result.replace(/void 0\b/g, 'undefined');

    // Hex numbers to decimal where helpful: 0x12a -> 298
    result = result.replace(/\b0x([0-9a-fA-F]+)\b/g, (match, hex) => {
        // Keep small hex or color codes intact if appropriate, otherwise convert
        const val = parseInt(hex, 16);
        return val.toString();
    });

    // Simplify obj['prop'] -> obj.prop when prop is a valid JS identifier
    result = result.replace(/\[\s*['"]([a-zA-Z_$][a-zA-Z0-9_$]*)['"]\s*\]/g, '.$1');

    return result;
}

function resolveStringArrays(code) {
    // Regex for standard obfuscator string array pattern:
    // var _0x1a2b = ['str1', 'str2', ...];
    // or const a = [...];
    const arrayRegex = /(?:var|const|let)\s+([a-zA-Z0-9_$]+)\s*=\s*(\[[^\]]{20,}\]);/s;
    const match = arrayRegex.exec(code);
    if (!match) {
        return code;
    }

    const arrayName = match[1];
    const arrayCode = match[0];
    console.log(`[*] Detected potential string array: '${arrayName}'`);

    // Find the shuffle / rotation function immediately following
    // e.g., (function(a, b) { ... })(arrayName, 0x123);
    const rotationRegex = new RegExp(`\\(function\\s*\\([a-zA-Z0-9_$,\\s]+\\)\\s*\\{.*?\\}\\)\\s*\\(\\s*${arrayName}\\s*,\\s*(?:0x[0-9a-fA-F]+|\\d+)\\s*\\);`, 's');
    const rotMatch = rotationRegex.exec(code);

    // Find the decoder function:
    // function _0xfunc(idx, key) { return arrayName[idx - offset]; }
    const decoderRegex = new RegExp(`function\\s+([a-zA-Z0-9_$]+)\\s*\\([^)]*\\)\\s*\\{.*?return\\s+${arrayName}.*?\\}`, 's');
    const decMatch = decoderRegex.exec(code);

    if (decMatch) {
        const decName = decMatch[1];
        console.log(`[*] Detected decoder function: '${decName}'`);

        try {
            // Build sandbox environment
            const sandbox = {};
            const context = vm.createContext(sandbox);

            let setupScript = arrayCode + '\n';
            if (rotMatch) {
                setupScript += rotMatch[0] + '\n';
            }
            setupScript += decMatch[0] + '\n';

            vm.runInContext(setupScript, context, { timeout: 2000 });

            // Test if decoder is callable
            if (typeof context[decName] === 'function') {
                console.log(`[+] Successfully initialized decoder in VM sandbox.`);

                // Find all calls: decName(123) or decName('0x1a') or decName(1, 'key')
                const callRegex = new RegExp(`\\b${decName}\\s*\\(\\s*([^)]+)\\s*\\)`, 'g');
                let replacedCount = 0;

                code = code.replace(callRegex, (fullCall, args) => {
                    try {
                        const evalCall = `${decName}(${args})`;
                        const resolvedVal = vm.runInContext(evalCall, context, { timeout: 100 });
                        if (typeof resolvedVal === 'string') {
                            replacedCount++;
                            return JSON.stringify(resolvedVal);
                        } else if (typeof resolvedVal === 'number' || typeof resolvedVal === 'boolean') {
                            replacedCount++;
                            return String(resolvedVal);
                        }
                    } catch (_) {}
                    return fullCall;
                });

                console.log(`[+] Replaced ${replacedCount} string array decoder calls with literal values!`);
            }
        } catch (err) {
            console.warn(`[-] VM execution of string array failed: ${err.message}`);
        }
    }

    return code;
}

function unpackWebpackModules(code, outDir) {
    console.log(`[*] Scanning for Webpack bundle/chunk structure...`);
    os_mkdir(outDir);

    // Match webpackJsonp or chunk format: [[chunkId], { 123: function(e,t,n){...}, 'abc': (e,t,n) => {...} }]
    const chunkRegex = /push\(\s*\[\s*\[[^\]]*\]\s*,\s*\{([\s\S]*?)\}\s*(?:,\s*\[[^\]]*\])?\s*\]\s*\)/g;
    let match = chunkRegex.exec(code);
    let extractedCount = 0;

    if (!match) {
        // Alternative: (function(modules) { ... })( { 0: function(...){...} } )
        const selfExecRegex = /\(\s*(?:function\s*\([a-zA-Z0-9_$]+\)|[a-zA-Z0-9_$]+)\s*\{[\s\S]*?\}\s*\)\s*\(\s*\{([\s\S]*?)\}\s*\)/;
        match = selfExecRegex.exec(code);
    }

    if (match && match[1]) {
        const modulesBlock = match[1];
        // Split modules by module id pattern: e.g. 123: function(...) or "abc": (function(...)
        const moduleRegex = /(?:^|,)\s*([0-9]+|['"][^'"]+['"])\s*:\s*(function\b[\s\S]*?|(?:\([^)]*\)|[a-zA-Z0-9_$]+)\s*=>[\s\S]*?)(?=(?:,\s*(?:[0-9]+|['"][^'"]+['"])\s*:)|$)/g;
        
        let m;
        while ((m = moduleRegex.exec(modulesBlock)) !== null) {
            let modId = m[1].replace(/['"]/g, '');
            let modBody = m[2].trim();
            const safeModName = `module_${modId.replace(/[^a-zA-Z0-9_-]/g, '_')}.js`;
            const modPath = path.join(outDir, safeModName);
            fs.writeFileSync(modPath, `// Webpack Module ID: ${modId}\nmodule.exports = ${modBody};\n`, 'utf-8');
            extractedCount++;
        }
    }

    if (extractedCount > 0) {
        console.log(`[+] Successfully extracted ${extractedCount} Webpack modules into: ${outDir}`);
    } else {
        console.log(`[-] No standard Webpack module dictionary pattern matched.`);
    }
}

function os_mkdir(dir) {
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
}

function main() {
    const args = process.argv.slice(2);
    if (args.length === 0 || args.includes('-h') || args.includes('--help')) {
        printUsage();
        process.exit(0);
    }

    const inputFile = args[0];
    if (!fs.existsSync(inputFile)) {
        console.error(`[-] Input file does not exist: ${inputFile}`);
        process.exit(1);
    }

    let outPath = null;
    let unpackWebpack = false;
    let useWebcrack = false;

    for (let i = 1; i < args.length; i++) {
        if (args[i] === '--out' || args[i] === '-o') {
            outPath = args[++i];
        } else if (args[i] === '--unpack-webpack') {
            unpackWebpack = true;
        } else if (args[i] === '--engine' && args[i + 1] === 'webcrack') {
            useWebcrack = true;
            i++;
        }
    }

    if (useWebcrack) {
        console.log(`[*] Invoking webcrack engine via npx...`);
        const targetDir = outPath || path.join(path.dirname(inputFile), path.basename(inputFile, '.js') + '_webcrack');
        try {
            execSync(`npx webcrack "${inputFile}" -o "${targetDir}"`, { stdio: 'inherit' });
            console.log(`[+] webcrack completed successfully -> ${targetDir}`);
            process.exit(0);
        } catch (e) {
            console.warn(`[-] webcrack failed or not installed. Falling back to built-in deobfuscator.`);
        }
    }

    console.log(`[*] Loading source file: ${inputFile}`);
    let code = fs.readFileSync(inputFile, 'utf-8');
    const originalLen = code.length;

    console.log(`[*] Step 1: Decoding hex and unicode escapes...`);
    code = decodeEscapeSequences(code);

    console.log(`[*] Step 2: Resolving string arrays and rotation shifts...`);
    code = resolveStringArrays(code);

    console.log(`[*] Step 3: Simplifying constant expressions and member access...`);
    code = simplifyConstants(code);

    if (unpackWebpack) {
        const webpackOutDir = outPath ? (fs.existsSync(outPath) && fs.statSync(outPath).isDirectory() ? outPath : path.join(path.dirname(outPath), 'webpack_modules')) : path.join(path.dirname(inputFile), 'webpack_modules');
        unpackWebpackModules(code, webpackOutDir);
    }

    const defaultOut = path.join(
        path.dirname(inputFile),
        path.basename(inputFile, path.extname(inputFile)) + '.deobf.js'
    );
    const finalOut = outPath && !fs.existsSync(outPath) && !outPath.endsWith('/') && !outPath.endsWith('\\') ? outPath : defaultOut;

    fs.writeFileSync(finalOut, code, 'utf-8');
    console.log(`[+] Deobfuscation complete!`);
    console.log(`    Original size: ${originalLen} bytes`);
    console.log(`    Output size  : ${code.length} bytes`);
    console.log(`    Saved to     : ${finalOut}`);
}

main();
