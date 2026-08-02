if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/app/sw.js')
    .catch(err => console.debug('SW registration skipped:', err.message));
}
