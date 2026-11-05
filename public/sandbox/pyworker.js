// Web Worker: Pyodide-ს აქ ვტვირთავთ და მოსწავლის კოდს აქ ვუშვებთ, ასე უსასრულო ციკლი გვერდს არ ყინავს:
// editor.js-ი 5 წამის შემდეგ Worker-ს terminate()-ით აჩერებს. ფაილი editor.js-ში Blob-ად იქცევა (გაუმჭვირვალე წარმოშობის
// გვერდიდან URL-ით Worker-ის შექმნა დაუშვებელია), ამიტომ აქ მხოლოდ აბსოლუტური URL-ებია და ყველაფერი init-ის შეტყობინებით მოდის.
'use strict';
let py = null;

self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (m.t === 'init') {
      importScripts(m.base + 'pyodide.js');
      py = await loadPyodide({ indexURL: m.base });   // მხოლოდ სტანდარტული ბიბლიოთეკა; პაკეტებს არ ვტვირთავთ
      py.runPython(m.runner);                         // runner.py-ის ტექსტი (იგივე, რასაც validate_content.py ამოწმებს)
      // ქსელი კოდიდან: ძირითადი დაცვა CSP-ია (connect-src მხოლოდ /vendor/pyodide/ და /sandbox/); ეს მეორე ფენაა
      for (const k of ['fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource', 'importScripts', 'Worker', 'SharedWorker']) {
        try { self[k] = undefined; } catch (_) { /* ignore */ }
      }
      postMessage({ t: 'ready' });
    } else if (m.t === 'run') {
      const fn = py.globals.get('run_json');
      const out = fn(m.code, JSON.stringify(m.stdin || []), JSON.stringify(m.checks || []));
      fn.destroy();
      postMessage({ t: 'result', id: m.id, data: JSON.parse(out) });
    }
  } catch (err) {
    postMessage({ t: 'fail', stage: m.t, msg: String((err && err.message) || err) });
  }
};
