function showOverviewError(error) {
  document.documentElement.dataset.overviewState = 'error';
  document.querySelector('#overview-loading').hidden = true;
  document.querySelector('#overview-viewport').setAttribute('aria-busy', 'false');
  document.querySelector('#overview-error').hidden = false;
  document.querySelector('#overview-error-message').textContent = error instanceof Error ? error.message : '参考配置の読み込みに失敗しました。';
  document.querySelector('#overview-retry').onclick = () => location.reload();
  for (const id of ['overview-controls', 'overview-part-controls']) document.getElementById(id).disabled = true;
  for (const button of document.querySelectorAll('button[data-step]')) button.disabled = true;
  for (const button of document.querySelectorAll('.overview-label')) button.disabled = true;
}

async function initializeOverview() {
  document.documentElement.dataset.overviewState = 'loading';
  try {
    if (location.protocol === 'file:') throw new Error('file:// では3Dデータを読めません。READMEのローカルHTTPでの開き方を使ってください。');
    const {startOverview} = await import('./overview.js');
    await startOverview(showOverviewError);
  } catch (error) {
    showOverviewError(error);
  }
}

initializeOverview();
