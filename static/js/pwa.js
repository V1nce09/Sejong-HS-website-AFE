// Service Worker 등록
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/static/sw.js").catch(console.error);
  });
}

// 설치 유도 배너 컨트롤
let deferredPrompt;
const installBtnId = "install-app-btn";
const installBannerId = "install-banner";

function showInstallControls() {
  const btn = document.getElementById(installBtnId);
  const banner = document.getElementById(installBannerId);
  if (btn && banner) {
    banner.style.display = "flex";
    btn.style.display = "inline-flex";
  }
}
function hideInstallControls() {
  const btn = document.getElementById(installBtnId);
  const banner = document.getElementById(installBannerId);
  if (btn) btn.style.display = "none";
  if (banner) banner.style.display = "none";
}

window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredPrompt = e;
  showInstallControls();
});

window.addEventListener("appinstalled", () => {
  deferredPrompt = null;
  hideInstallControls();
});

// 버튼 핸들러
window.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById(installBtnId);
  if (btn) {
    btn.addEventListener("click", async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
      hideInstallControls();
    });
  }
});
