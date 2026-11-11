function showEnclosureError(error) {
  document.documentElement.dataset.enclosureState = 'error';
  document.querySelector('#enclosure-loading').hidden = true;
  document.querySelector('#enclosure-viewport').setAttribute('aria-busy', 'false');
  document.querySelector('#enclosure-error').hidden = false;
  document.querySelector('#enclosure-error-message').textContent = error instanceof Error ? error.message : '筐体データの読み込みに失敗しました。';
  document.querySelector('#enclosure-retry').onclick = () => location.reload();
  for (const id of ['enclosure-controls', 'enclosure-parts-controls']) document.getElementById(id).disabled = true;
  for (const button of document.querySelectorAll('button[data-focus]')) button.disabled = true;
}

async function initializeEnclosure() {
  document.documentElement.dataset.enclosureState = 'loading';
  try {
    if (location.protocol === 'file:') throw new Error('file:// では3Dデータを読めません。READMEのローカルHTTPでの開き方を使ってください。');
    const {startEnclosure} = await import('./enclosure.js');
    await startEnclosure(showEnclosureError);
  } catch (error) {
    showEnclosureError(error);
  }
}

initializeEnclosure();
