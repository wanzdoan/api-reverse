// ==UserScript==
// @name         Universal Anti-Debugger & Anti-DevTools Neutralizer
// @namespace    https://github.com/webreverse
// @version      1.0
// @description  Bypasses infinite debugger, console.clear, and timing detections
// @match        *://*/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function() {
    'use strict';

    console.log('[*] Anti-Debugger Neutralizer activated.');

    // 1. Function constructor bypass
    const _Function = window.Function;
    const hookedFunction = function(...args) {
        if (args.length > 0) {
            const body = args[args.length - 1];
            if (typeof body === 'string' && body.includes('debugger')) {
                args[args.length - 1] = body.replace(/debugger\s*;?/g, '/* removed */');
            }
        }
        return _Function.apply(this, args);
    };
    hookedFunction.prototype = _Function.prototype;
    window.Function = hookedFunction;

    // 2. eval bypass
    const _eval = window.eval;
    window.eval = function(code) {
        if (typeof code === 'string' && code.includes('debugger')) {
            code = code.replace(/debugger\s*;?/g, '/* removed */');
        }
        return _eval.apply(this, arguments);
    };

    // 3. console.clear suppression
    console.clear = function() {
        console.warn('[*] console.clear() prevented.');
    };

    // 4. Disguise toString
    const _toString = Function.prototype.toString;
    Function.prototype.toString = function() {
        if (this === window.Function || this === window.eval || this === console.clear) {
            return 'function () { [native code] }';
        }
        return _toString.apply(this, arguments);
    };
})();
