function showError(error) {
  document.documentElement.dataset.motionState = 'error';
  document.getElementById('loading').hidden = true;
  document.getElementById('viewport').setAttribute('aria-busy', 'false');
  document.getElementById('load-error').hidden = false;
  document.getElementById('error-message').textContent = error instanceof Error ? error.message : '動作データを読み込めません。';
  for (const id of ['view-controls', 'motion-controls', 'inspection-controls']) document.getElementById(id).disabled = true;
  document.getElementById('retry').onclick = () => location.reload();
}

async function initialize() {
  document.documentElement.dataset.motionState = 'loading';
  const video = document.getElementById('explanation-video');
  video.defaultMuted = true;
  video.muted = true;
  video.volume = 0;
  video.addEventListener('error', () => {
    document.getElementById('video-error').textContent = '説明動画を読み込めません。media/を含む公開セットを確認してください。';
  });
  try {
    if (location.protocol === 'file:') throw new Error('3Dはfile://では開けません。docs/MOTION.mdのローカルHTTP起動手順を使ってください。');
    const {start} = await import('./motion.js');
    await start(showError);
  } catch (error) {
    showError(error);
  }
}
initialize();
