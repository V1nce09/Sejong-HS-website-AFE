(() => {
  'use strict';

  let deferredPrompt = null;
  const buttons = () => Array.from(document.querySelectorAll('[data-pwa-install]'));
  const standalone = () => window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  const isiOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent);

  function setInstallVisible(visible) {
    buttons().forEach((button) => { button.hidden = !visible; });
  }

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js', { scope: '/' }).catch((error) => {
        console.warn('PWA service worker registration failed:', error);
      });
    });
  }

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    deferredPrompt = event;
    if (!standalone()) setInstallVisible(true);
  });

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    setInstallVisible(false);
  });

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-pwa-install]');
    if (!button) return;

    if (standalone()) {
      setInstallVisible(false);
      return;
    }

    if (deferredPrompt) {
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
      setInstallVisible(false);
      return;
    }

    if (isiOS()) {
      window.alert('iPhone/iPad에서는 Safari의 공유 버튼을 누른 뒤 “홈 화면에 추가”를 선택하세요.');
      return;
    }

    window.alert('브라우저 메뉴에서 “앱 설치” 또는 “홈 화면에 추가”를 선택하세요.');
  });

  document.addEventListener('DOMContentLoaded', () => {
    if (standalone()) {
      setInstallVisible(false);
    } else if (isiOS()) {
      setInstallVisible(true);
      buttons().forEach((button) => { button.textContent = '홈 화면에 추가'; });
    }
  });
})();
