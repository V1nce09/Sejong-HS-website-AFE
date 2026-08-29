(() => {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const token = meta ? meta.content : '';
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const opts = { ...init };
    const method = String(opts.method || 'GET').toUpperCase();
    if (['POST','PUT','PATCH','DELETE'].includes(method) && token) {
      const headers = new Headers(opts.headers || {});
      headers.set('X-CSRFToken', token);
      opts.headers = headers;
    }
    return originalFetch(input, opts);
  };
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('form').forEach(form => {
      const method = String(form.getAttribute('method') || 'GET').toUpperCase();
      if (['POST','PUT','PATCH','DELETE'].includes(method) && token && !form.querySelector('input[name="csrf_token"]')) {
        const input = document.createElement('input'); input.type='hidden'; input.name='csrf_token'; input.value=token; form.appendChild(input);
      }
    });
  });
})();
