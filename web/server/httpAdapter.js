const MAX_BODY_BYTES = 256 * 1024;

function jsonError(status, message) {
  return Response.json({ error: message }, { status, headers: { 'Cache-Control': 'no-store' } });
}

/** Bridge raw Node requests for local middleware, with bounded streaming input. */
export function nodeHandler(handler, { maxBodyBytes = MAX_BODY_BYTES } = {}) {
  return async function handleNodeRequest(incoming, outgoing) {
    let exceeded = false;
    let finished = false;
    let detach = () => {};
    const length = incoming.headers['content-length'];
    if (typeof length === 'string' && /^\d+$/.test(length) && Number(length) > maxBodyBytes) {
      outgoing.statusCode = 413;
      outgoing.setHeader('Content-Type', 'application/json');
      outgoing.setHeader('Cache-Control', 'no-store');
      incoming.resume();
      outgoing.end(JSON.stringify({ error: 'Request body too large' }));
      return;
    }

    try {
      const headers = new Headers();
      for (const [key, value] of Object.entries(incoming.headers)) {
        if (Array.isArray(value)) value.forEach(item => headers.append(key, item));
        else if (value !== undefined) headers.set(key, value);
      }
      const method = incoming.method ?? 'GET';
      let body;
      if (method !== 'GET' && method !== 'HEAD') {
        if (incoming.body !== undefined) {
          // Production uses native Request handlers. Local middleware must run
          // before any body parser consumes or rewrites the original bytes.
          throw new Error('Body parser must be disabled');
        }
        body = new ReadableStream({
          start(controller) {
            let bytes = 0;
            const data = chunk => {
              bytes += chunk.byteLength;
              if (bytes > maxBodyBytes) {
                exceeded = true;
                finished = true;
                detach();
                controller.error(new Error('Request body too large'));
                incoming.resume();
                return;
              }
              controller.enqueue(new Uint8Array(chunk));
              if (controller.desiredSize <= 0) incoming.pause();
            };
            const end = () => { finished = true; detach(); controller.close(); };
            const error = () => { finished = true; detach(); controller.error(new Error('Request interrupted')); };
            detach = () => {
              incoming.off('data', data);
              incoming.off('end', end);
              incoming.off('error', error);
              incoming.off('aborted', error);
            };
            incoming.on('data', data);
            incoming.on('end', end);
            incoming.on('error', error);
            incoming.on('aborted', error);
            incoming.pause();
          },
          pull() { incoming.resume(); },
          cancel() { finished = true; detach(); incoming.resume(); },
        });
      }
      // Authorization/origin decisions must use configured trusted origins,
      // never an untrusted Host or X-Forwarded-Host header.
      const url = new URL(incoming.url ?? '/', 'http://localhost');
      const request = new Request(url, { method, headers, ...(body ? { body, duplex: 'half' } : {}) });
      let response;
      try { response = await handler(request); }
      catch { response = jsonError(500, 'Request unavailable'); }
      if (exceeded) response = jsonError(413, 'Request body too large');
      outgoing.statusCode = response.status;
      response.headers.forEach((value, key) => {
        if (key !== 'set-cookie') outgoing.setHeader(key, value);
      });
      const cookies = response.headers.getSetCookie();
      if (cookies.length) outgoing.setHeader('Set-Cookie', cookies);
      outgoing.end(method === 'HEAD' ? undefined : Buffer.from(await response.arrayBuffer()));
    } catch {
      if (!outgoing.headersSent) {
        outgoing.statusCode = exceeded ? 413 : 500;
        outgoing.setHeader('Content-Type', 'application/json');
        outgoing.setHeader('Cache-Control', 'no-store');
      }
      outgoing.end(JSON.stringify({ error: exceeded ? 'Request body too large' : 'Request unavailable' }));
    } finally {
      detach();
      if (!finished) incoming.resume();
    }
  };
}
