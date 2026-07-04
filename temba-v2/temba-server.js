/* temba-server.js — thin fetch wrapper (Railway has no cold starts) */
(function () {
  window._serverFetch = function serverFetch(url, options) {
    return fetch(url, options);
  };
})();
