document.addEventListener('DOMContentLoaded', () => {
  const body=document.body; if(body.dataset.isAdmin!=='1') return;
  const $=id=>document.getElementById(id);
  const esc=(v='')=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function api(url, options={}){ const r=await fetch(url,options); let d={}; try{d=await r.json();}catch(_){} if(!r.ok) throw new Error(d.message||'요청에 실패했습니다.'); return d; }
  async function loadSecurity(){
    try{
      const [a,e,b]=await Promise.all([api('/api/admin/security/login_attempts'),api('/api/admin/security/events'),api('/api/admin/security/blacklist')]);
      const ah=$('admin-login-attempts'), eh=$('admin-security-events'), bh=$('admin-blacklist');
      ah.innerHTML=(a.attempts||[]).length ? a.attempts.map(x=>`<div class="admin-audit-item"><div><strong>${esc(x.userid||'(알 수 없음)')} · ${esc(x.ip)}</strong><span>실패 ${Number(x.failed_count)}회${x.locked_until?' · 제한 중':''}</span></div><time>${esc(String(x.last_failed_at||'').replace('T',' ').slice(0,16))}</time></div>`).join('') : '<div class="admin-empty-state">기록이 없습니다.</div>';
      eh.innerHTML=(e.events||[]).length ? e.events.map(x=>`<div class="admin-audit-item"><div><strong>${esc(x.event_type)} · ${esc(x.userid||'비로그인')}</strong><span>${esc(x.method)} ${esc(x.path)} · ${esc(x.details)}</span></div><time>${esc(String(x.created_at||'').replace('T',' ').slice(0,16))}</time></div>`).join('') : '<div class="admin-empty-state">기록이 없습니다.</div>';
      bh.innerHTML=(b.items||[]).length ? b.items.map(x=>`<div class="admin-audit-item"><div><strong>${esc(x.target)}${x.name?' · '+esc(x.name):''}</strong><span>${esc(x.reason)}${x.ip?' · '+esc(x.ip):''}</span></div><button type="button" class="text-button security-unblock" data-id="${Number(x.id)}">해제</button></div>`).join('') : '<div class="admin-empty-state">활성 블랙리스트가 없습니다.</div>';
      bh.querySelectorAll('.security-unblock').forEach(btn=>btn.addEventListener('click',async()=>{if(!confirm('이 블랙리스트를 해제할까요?'))return;try{await api(`/api/admin/security/blacklist/${btn.dataset.id}`,{method:'DELETE'});loadSecurity();}catch(err){alert(err.message);}}));
    }catch(err){ const msg=$('admin-security-message'); if(msg){msg.textContent=err.message;msg.className='form-message error';} }
  }
  $('admin-security-refresh')?.addEventListener('click',loadSecurity);
  $('security-block-submit')?.addEventListener('click',async()=>{
    const kind=$('security-block-kind').value, value=$('security-block-value').value.trim(), reason=$('security-block-reason').value.trim();
    if(!value){alert('차단 대상을 입력해주세요.');return;}
    if(!confirm('이 대상을 블랙리스트에 등록할까요?'))return;
    try{const d=await api('/api/admin/security/blacklist',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,value,reason})});$('security-block-value').value='';$('security-block-reason').value='';$('admin-security-message').textContent=d.message; $('admin-security-message').className='form-message success'; loadSecurity();}catch(err){$('admin-security-message').textContent=err.message;$('admin-security-message').className='form-message error';}
  });
  loadSecurity();
});
