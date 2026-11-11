function showError(error) {
  document.documentElement.dataset.viewerState = 'error';
  document.querySelector('#loading').hidden = true;
  document.querySelector('#viewport').setAttribute('aria-busy', 'false');
  document.querySelector('#load-error').hidden = false;
  document.querySelector('#error-message').textContent = error instanceof Error ? error.message : '部品データを読み込めませんでした。';
  document.querySelector('#retry').onclick = () => window.location.reload();
  for (const id of ['bench-controls', 'part-controls']) document.getElementById(id).disabled = true;
  for (const button of document.querySelectorAll('button[data-mode]')) button.disabled = true;
}

async function initialize() {
  document.documentElement.dataset.viewerState = 'loading';
  try {
    if (location.protocol === 'file:') throw new Error('file:// では3Dデータを読み込めません。READMEのローカルHTTPでの開き方を使ってください。');
    const {start} = await import('./app.js');
    await start(showError);
  } catch (error) {
    showError(error);
  }
}

initialize();
