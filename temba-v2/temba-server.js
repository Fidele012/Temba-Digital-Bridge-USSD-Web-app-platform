/* temba-server.js — handles Render free-tier cold-start retries
 *
 * Exports one global: window._serverFetch(url, options)
 *   Drop-in for fetch(). On network failure it shows a "waking up" banner
 *   and retries every 10 s for up to 60 s. If the server is still down after
 *   that, the banner updates to a "retry" prompt and the error is re-thrown.
 */
(function () {
  let _banner = null;

  function _showBanner(attempt, max) {
    if (!_banner) {
      _banner = document.createElement('div');
      _banner.style.cssText = [
        'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:99999',
        'background:#1565C0', 'color:#fff', 'text-align:center',
        'padding:10px 16px', 'font-size:13px', 'font-weight:600',
        'display:flex', 'align-items:center', 'justify-content:center', 'gap:8px',
      ].join(';');
      document.body.prepend(_banner);
    }
    _banner.innerHTML =
      '<span style="display:inline-block;animation:spin 1s linear infinite;font-size:16px">⏳</span>' +
      ` Connecting to server&hellip; this takes up to 2 minutes on first use. Please wait. (${attempt}/${max})`;
  }

  function _showError() {
    if (!_banner) return;
    _banner.style.background = '#B71C1C';
    _banner.innerHTML =
      '⚠️ Server did not respond. ' +
      '<a href="javascript:location.reload()" style="color:#fff;text-decoration:underline;font-weight:700;">Click to try again</a> — it should work on the next attempt.';
  }

  function _hideBanner() {
    if (_banner) { _banner.remove(); _banner = null; }
  }

  /* Add the spin keyframe once */
  if (!document.getElementById('_sf_style')) {
    const s = document.createElement('style');
    s.id = '_sf_style';
    s.textContent = '@keyframes spin{to{transform:rotate(360deg)}}';
    document.head.appendChild(s);
  }

  window._serverFetch = async function serverFetch(url, options = {}) {
    /* On localhost/127.0.0.1 the server either works or it doesn't — no cold starts.
       Skip the retry banner entirely and fail fast so signin falls through to local auth. */
    const isLocal = ['localhost', '127.0.0.1'].includes(window.location.hostname);
    if (isLocal) return fetch(url, options);

    const MAX_RETRIES = 12;  /* 12 × 10 s = 120 s total — Render free tier can take up to 2 min */
    const DELAY_MS    = 10000;

    for (let i = 0; i <= MAX_RETRIES; i++) {
      try {
        const resp = await fetch(url, options);
        _hideBanner();
        return resp;
      } catch (err) {
        if (i >= MAX_RETRIES) { _showError(); throw err; }
        _showBanner(i + 1, MAX_RETRIES);
        await new Promise(r => setTimeout(r, DELAY_MS));
      }
    }
  };
})();
