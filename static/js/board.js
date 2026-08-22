document.addEventListener('DOMContentLoaded', () => {
  const esc = (value = '') => String(value).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));

  async function api(url, options = {}) {
    const response = await fetch(url, options);
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.message || '요청에 실패했습니다.');
    return data;
  }

  async function loadMyClasses() {
    const host = document.getElementById('my-classes-list');
    if (!host) return;
    try {
      const data = await api('/api/my_classes');
      const classes = data.classes || [];
      if (!classes.length) {
        host.innerHTML = '<li class="board-empty-class">가입된 클래스가 없습니다.</li>';
        return;
      }
      host.innerHTML = classes.map(c => {
        const href = `/class/${encodeURIComponent(c.grade)}/${encodeURIComponent(c.classroom)}`;
        const unread = Number(c.unread_count || 0);
        return `<li><a href="${href}"><span>${esc(c.display_name || '')}</span>${unread > 0 ? `<b class="sidebar-unread-count">${unread}</b>` : ''}</a></li>`;
      }).join('');
    } catch (_) {
      host.innerHTML = '<li class="board-empty-class">클래스를 불러오지 못했습니다.</li>';
    }
  }

  const overlay = document.getElementById('class-popup-overlay');
  const inviteInput = document.getElementById('new-class-name-input');
  document.querySelector('.add-class-btn')?.addEventListener('click', () => {
    if (!overlay) return;
    overlay.style.display = 'flex';
    if (inviteInput) { inviteInput.value = ''; inviteInput.focus(); }
  });
  document.getElementById('add-class-cancel-btn')?.addEventListener('click', () => {
    if (overlay) overlay.style.display = 'none';
  });
  overlay?.addEventListener('click', e => {
    if (e.target === overlay) overlay.style.display = 'none';
  });
  document.getElementById('add-class-submit-btn')?.addEventListener('click', async () => {
    const code = inviteInput?.value.trim() || '';
    try {
      const data = await api('/api/add_class_by_code', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({invite_code: code})
      });
      alert(data.message || '클래스를 추가했습니다.');
      if (overlay) overlay.style.display = 'none';
      await loadMyClasses();
    } catch (e) {
      alert(e.message);
    }
  });

  const dots = document.querySelector('.dots-btn');
  const dropdown = document.querySelector('.profile-dropdown');
  const postsHost = document.querySelector('.my-posts-list');
  let postsLoaded = false;

  async function loadMyPosts() {
    if (!postsHost) return;
    postsHost.innerHTML = '<span class="my-posts-loading">불러오는 중...</span>';
    try {
      const data = await api('/api/my_posts');
      const posts = data.posts || [];
      postsLoaded = true;
      if (!posts.length) {
        postsHost.innerHTML = '<span class="my-posts-empty">작성한 글이 없습니다.</span>';
        return;
      }
      postsHost.innerHTML = posts.map(post => {
        const date = String(post.created_at || '').slice(0, 10);
        return `<a class="my-post-item" href="${esc(post.url)}"><strong>${esc(post.title)}</strong><span>${esc(post.board_name)} · ${esc(date)}</span></a>`;
      }).join('');
    } catch (e) {
      postsHost.innerHTML = `<span class="my-posts-empty">${esc(e.message)}</span>`;
    }
  }

  function closeProfileMenu() {
    if (!dropdown || !dots) return;
    dropdown.setAttribute('aria-hidden', 'true');
    dots.setAttribute('aria-expanded', 'false');
  }

  dots?.addEventListener('click', async e => {
    e.stopPropagation();
    if (!dropdown) return;
    const willOpen = dropdown.getAttribute('aria-hidden') !== 'false';
    dropdown.setAttribute('aria-hidden', willOpen ? 'false' : 'true');
    dots.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    if (willOpen && !postsLoaded) await loadMyPosts();
  });
  dropdown?.addEventListener('click', e => e.stopPropagation());
  document.addEventListener('click', closeProfileMenu);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeProfileMenu(); });

  document.querySelectorAll('.pin-post-btn').forEach(button => {
    button.addEventListener('click', async e => {
      e.preventDefault();
      e.stopPropagation();
      button.disabled = true;
      try {
        await api(`/api/posts/${button.dataset.postId}/pin`, {method: 'POST'});
        location.reload();
      } catch (err) {
        alert(err.message);
        button.disabled = false;
      }
    });
  });

  document.querySelectorAll('.delete-post-btn').forEach(button => {
    button.addEventListener('click', async e => {
      e.preventDefault();
      e.stopPropagation();
      if (!confirm('이 게시물을 삭제할까요? 삭제한 글은 복구할 수 없습니다.')) return;
      button.disabled = true;
      try {
        const data = await api(`/api/posts/${button.dataset.postId}/delete`, {method: 'POST'});
        location.href = data.redirect_url || '/';
      } catch (err) {
        alert(err.message);
        button.disabled = false;
      }
    });
  });

  window.addEventListener('pageshow', e => { if (e.persisted) location.reload(); });

  loadMyClasses();
});
