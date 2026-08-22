document.addEventListener('DOMContentLoaded', () => {
  const body = document.body;
  const initialDate = body.dataset.initialDate;
  const authenticated = body.dataset.authenticated === '1';
  const isAdmin = body.dataset.isAdmin === '1';
  const DAYS = ['월', '화', '수', '목', '금'];
  const DAILY_PERIODS = {1:[7,7,6,7,7], 2:[7,7,6,7,5]};
  const ELECTIVE_SLOTS = new Set(['0:1','0:2','0:5','0:6','1:2','1:5','2:2','2:3','2:5','3:1','3:2','3:3','4:1','4:2','4:4']);
  const SUBJECT_GROUPS = {
    humanities:['윤리와 사상','법과 사회','한국지리 탐구','경제','일본어 회화','사회 문제 탐구','동아시아 역사 기행'],
    science:['역학과 에너지','물질과 에너지','세포와 물질대사','지구시스템과학','융합과학 탐구','인공지능 기초','지식 재산 일반','인공지능 수학']
  };
  const cache = {};

  const $ = (id) => document.getElementById(id);
  const esc = (value='') => String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const formatDate = value => value && value.length === 8 ? `${Number(value.slice(4,6))}월 ${Number(value.slice(6,8))}일` : value;
  const weekday = value => { const d = new Date(`${value.slice(0,4)}-${value.slice(4,6)}-${value.slice(6,8)}T12:00:00`); return ['일','월','화','수','목','금','토'][d.getDay()]; };
  const today = initialDate;
  $('today-label').textContent = `${formatDate(today)} ${weekday(today)}요일`;

  async function api(url, options={}) {
    const response = await fetch(url, options);
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) { const e = new Error(data.message || '요청에 실패했습니다.'); e.status = response.status; e.data = data; throw e; }
    return data;
  }

  function setSection(name) {
    document.querySelectorAll('.portal-section').forEach(el => el.classList.toggle('active', el.dataset.section === name));
    document.querySelectorAll('.portal-nav-item').forEach(el => el.classList.toggle('active', el.dataset.nav === name));
    history.replaceState(null, '', `#${name}`);
    if (name === 'profile') loadProfile();
    if (name === 'timetable') loadTimetable();
    if (name === 'boards') loadBoards();
    if (name === 'meals') loadMeals();
    if (name === 'news') { loadSchedule(); loadAnnouncements(); }
    if (name === 'about') loadSiteInfo();
    if (name === 'admin' && isAdmin) loadAdminPanel();
  }
  document.querySelectorAll('[data-nav]').forEach(el => el.addEventListener('click', e => { e.preventDefault(); setSection(el.dataset.nav); }));
  document.querySelectorAll('[data-jump]').forEach(el => el.addEventListener('click', () => setSection(el.dataset.jump)));
  const hash = location.hash.replace('#',''); if (document.querySelector(`[data-section="${hash}"]`)) setSection(hash);

  async function loadMeals() {
    if (!cache.meals) cache.meals = api(`/api/week_meals?date=${today}`).catch(() => ({days:[]}));
    const data = await cache.meals;
    const todayData = (data.days || []).find(d => d.date === today);
    renderMealDay($('home-meal'), todayData);
    const host = $('week-meals');
    if (!host) return;
    if (!data.days?.length) { host.innerHTML = '<div class="empty-panel">이번주 급식 정보가 없습니다.</div>'; return; }
    host.innerHTML = data.days.map(day => `<article class="meal-day-card ${day.date===today?'today':''}"><div class="meal-day-head"><strong>${day.day_name}요일</strong><span>${formatDate(day.date)}</span></div>${mealMarkup(day.meals)}</article>`).join('');
  }
  function mealMarkup(meals=[]) {
    if (!meals.length) return '<p class="muted">급식 정보 없음</p>';
    return meals.map(m => `<div class="meal-entry"><span class="meal-type">${esc(m.time)}</span><p>${esc(m.menu).replace(/\n/g,'<br>')}</p></div>`).join('');
  }
  function renderMealDay(host, day) { if (!host) return; host.innerHTML = day ? mealMarkup(day.meals) : '<p class="muted">오늘 급식 정보가 없습니다.</p>'; }

  async function loadWeather() {
    const host = $('home-weather');
    try {
      const data = await api('/api/weather'); const w = data.weather || {};
      if (w.temperature == null) throw new Error();
      host.innerHTML = `<div class="weather-main"><strong>${esc(w.condition)}</strong><span>${esc(w.temperature)}°</span></div><div class="weather-meta"><span>체감 ${esc(w.apparent_temperature)}°</span><span>습도 ${esc(w.humidity)}%</span><span>강수확률 ${esc(w.precipitation_probability ?? '-')}%</span><span>${esc(w.min_temperature)}° / ${esc(w.max_temperature)}°</span></div>`;
    } catch (_) { host.innerHTML = '<p class="muted">날씨 정보를 불러오지 못했습니다.</p>'; }
  }

  async function fetchPersonalTimetable() {
    if (!authenticated) return null;
    if (!cache.timetable) cache.timetable = api(`/api/personal_timetable?date=${today}`).catch(e => ({error:e.data || {message:e.message}}));
    return cache.timetable;
  }
  async function loadTimetable() {
    const host = $('week-timetable'), home = $('home-timetable'), alert = $('timetable-change-alert');
    if (!authenticated) { const msg='<div class="empty-panel">로그인 후 내 시간표를 사용할 수 있습니다.</div>'; if(host)host.innerHTML=msg;if(home)home.innerHTML='<p class="muted">로그인 후 확인할 수 있습니다.</p>';return; }
    const data = await fetchPersonalTimetable();
    if (!data || data.error) {
      const message = data?.error?.message || '시간표 설정에서 먼저 반을 등록해주세요.';
      if(host)host.innerHTML=`<div class="empty-panel">${esc(message)}</div>`; if(home)home.innerHTML=`<p class="muted">${esc(message)}</p>`; return;
    }
    const alerts = data.alerts || [];
    if (alert) { alert.hidden = !alerts.length; alert.innerHTML = alerts.length ? `<strong>시간표 변경 ${alerts.length}건</strong>${alerts.map(a=>`<span>${a.day_name} ${a.period}교시: ${esc(a.from)} → <b>${esc(a.to)}</b></span>`).join('')}` : ''; }
    if(host) host.innerHTML = timetableMarkup(data);
    const todayObj = (data.days||[]).find(d => d.date === today);
    if(home) home.innerHTML = todayObj ? `<div class="today-periods">${todayObj.cells.filter(c=>c.active).map(c=>`<div class="today-period ${c.changed?'changed':''}"><span>${c.period}</span><div class="today-subject"><strong>${esc(c.subject)}</strong>${c.elective_room?`<small class="elective-room">${esc(c.elective_room)}</small>`:''}</div></div>`).join('')}</div>` : '<p class="muted">오늘 수업이 없습니다.</p>';
  }
  function timetableMarkup(data) {
    const days = data.days || [];
    return `<div class="timetable-scroll"><table class="portal-timetable"><thead><tr><th>교시</th>${days.map(d=>`<th>${d.day_name}<small>${formatDate(d.date)}</small></th>`).join('')}</tr></thead><tbody>${Array.from({length:7},(_,i)=>i+1).map(period=>`<tr><th>${period}</th>${days.map(d=>{const c=d.cells.find(x=>x.period===period)||{}; if(!c.active)return '<td class="inactive">—</td>'; return `<td class="${c.changed?'changed':''} ${c.elective?'elective':''}">${c.changed?`<span class="change-tag">${c.change_type==='removed'?'없어짐':'변경'}</span>`:''}<strong>${esc(c.subject)}</strong>${c.elective_room?`<small class="elective-room">${esc(c.elective_room)}</small>`:''}</td>`;}).join('')}</tr>`).join('')}</tbody></table></div>`;
  }

  async function loadProfile() {
    if (!authenticated) { $('profile-guest').hidden=false; $('profile-content').hidden=true; return; }
    try { const d=await api('/api/user_profile'); const u=d.user; $('profile-content').hidden=false; $('profile-guest').hidden=true; $('profile-name').textContent=u.name||'-'; $('profile-student-no').textContent=u.is_admin?'관리자':(u.student_no||'미등록'); $('profile-name-input').value=u.name||'';  if(u.is_admin)$('profile-edit-toggle').hidden=true; }
    catch (_) { $('profile-content').hidden=true; $('profile-guest').hidden=false; }
  }
  $('profile-edit-toggle')?.addEventListener('click',()=>{$('profile-edit-form').hidden=false;$('profile-edit-toggle').hidden=true;});
  $('profile-edit-cancel')?.addEventListener('click',()=>{$('profile-edit-form').hidden=true;$('profile-edit-toggle').hidden=false;});
  $('profile-edit-form')?.addEventListener('submit',async e=>{e.preventDefault(); const msg=$('profile-edit-message'); try{const d=await api('/api/user_profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('profile-name-input').value})});msg.textContent=d.message;msg.className='form-message success';await loadProfile();setTimeout(()=>location.reload(),500);}catch(err){msg.textContent=err.message;msg.className='form-message error';}});

  $('password-edit-toggle')?.addEventListener('click',()=>{$('password-change-form').hidden=false;$('password-edit-toggle').hidden=true;});
  $('password-change-cancel')?.addEventListener('click',()=>{const form=$('password-change-form');form.reset();form.hidden=true;$('password-edit-toggle').hidden=false;$('password-change-message').textContent='';});
  $('password-change-form')?.addEventListener('submit',async e=>{
    e.preventDefault();
    const msg=$('password-change-message');
    try{
      const d=await api('/api/change_password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:$('current-password').value,new_password:$('new-password').value,new_password2:$('new-password2').value})});
      msg.textContent=d.message;msg.className='form-message success';e.target.reset();
      setTimeout(()=>{e.target.hidden=true;$('password-edit-toggle').hidden=false;msg.textContent='';},800);
    }catch(err){msg.textContent=err.message;msg.className='form-message error';}
  });

  async function loadBoards() {
    const host=$('boards-list');
    if(!authenticated){host.innerHTML='<div class="empty-panel">로그인 후 가입된 게시판을 확인할 수 있습니다.</div>';return;}
    try{const d=await api('/api/my_classes'); const list=d.classes||[]; host.innerHTML=list.length?list.map(c=>`<a class="board-card" href="/class/${encodeURIComponent(c.grade)}/${encodeURIComponent(c.classroom)}"><span class="board-icon">#</span><div><strong>${esc(c.display_name||`${c.grade}학년 ${c.classroom}반`)}</strong><small>${Number(c.unread_count||0)>0?`읽지 않음 ${Number(c.unread_count)}`:'게시판 열기'}</small></div>${Number(c.unread_count||0)>0?`<span class="board-unread-count">${Number(c.unread_count)}</span>`:''}</a>`).join(''):'<div class="empty-panel">가입된 게시판이 없습니다.</div>';}
    catch(e){host.innerHTML=`<div class="empty-panel">${esc(e.message)}</div>`;}
  }
  $('open-add-board')?.addEventListener('click',()=>{if(!authenticated){location.href='/login';return;}$('add-board-overlay').hidden=false;});
  $('board-add-submit')?.addEventListener('click',async()=>{const msg=$('board-add-message');try{const d=await api('/api/add_class_by_code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({invite_code:$('board-invite-code').value.trim()})});msg.textContent=d.message;msg.className='form-message success';setTimeout(()=>{ $('add-board-overlay').hidden=true; loadBoards(); },500);}catch(e){msg.textContent=e.message;msg.className='form-message error';}});

  async function loadSchedule(){ if(!cache.schedule)cache.schedule=api(`/api/school_schedule?date=${today}`).catch(()=>({events:[]})); const d=await cache.schedule; const host=$('school-schedule'); host.innerHTML=d.events?.length?d.events.map(ev=>`<div class="timeline-item"><div class="timeline-date"><strong>${formatDate(ev.date)}</strong><span>${weekday(ev.date)}</span></div><div><strong>${esc(ev.name||'학사 일정')}</strong>${ev.content?`<p>${esc(ev.content)}</p>`:''}<div class="grade-badges">${[1,2,3].filter(g=>ev[`grade${g}`]).map(g=>`<span>${g}학년</span>`).join('')}</div></div></div>`).join(''):'<div class="empty-panel">조회 기간의 학사일정이 없습니다.</div>'; }
  async function loadAnnouncements(){ const host=$('announcements-list');try{const d=await api('/api/announcements');host.innerHTML=d.announcements?.length?d.announcements.map(a=>`<article class="announcement-item"><div><strong>${esc(a.title)}</strong><time>${new Date(a.created_at).toLocaleDateString('ko-KR')}</time></div>${a.content?`<p>${esc(a.content).replace(/\n/g,'<br>')}</p>`:''}${isAdmin?`<button class="announcement-delete" data-id="${a.id}">삭제</button>`:''}</article>`).join(''):'<div class="empty-panel">등록된 공지가 없습니다.</div>';host.querySelectorAll('.announcement-delete').forEach(b=>b.addEventListener('click',async()=>{if(confirm('이 공지를 삭제할까요?')){await api(`/api/announcements/${b.dataset.id}`,{method:'DELETE'});loadAnnouncements();}}));}catch(e){host.innerHTML=`<div class="empty-panel">${esc(e.message)}</div>`;}}
  $('announcement-write-toggle')?.addEventListener('click',()=>{$('announcement-form').hidden=false;});
  $('announcement-cancel')?.addEventListener('click',()=>{$('announcement-form').hidden=true;});
  $('announcement-form')?.addEventListener('submit',async e=>{e.preventDefault();try{await api('/api/announcements',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('announcement-title').value,content:$('announcement-content').value})});e.target.reset();e.target.hidden=true;loadAnnouncements();}catch(err){alert(err.message);}});

  async function loadSiteInfo(){try{const d=await api('/api/site_info');$('site-purpose').textContent=d.purpose||'등록된 내용이 없습니다.';$('site-team').textContent=d.team||'등록된 내용이 없습니다.'; if(isAdmin){$('site-purpose-input').value=d.purpose||'';$('site-team-input').value=d.team||'';}}catch(_){} }
  $('site-info-edit-toggle')?.addEventListener('click',()=>{$('site-info-view').hidden=true;$('site-info-form').hidden=false;});
  $('site-info-cancel')?.addEventListener('click',()=>{$('site-info-form').hidden=true;$('site-info-view').hidden=false;});
  $('site-info-form')?.addEventListener('submit',async e=>{e.preventDefault();const msg=$('site-info-message');try{const d=await api('/api/site_info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({purpose:$('site-purpose-input').value,team:$('site-team-input').value})});msg.textContent=d.message;msg.className='form-message success';await loadSiteInfo();setTimeout(()=>{$('site-info-form').hidden=true;$('site-info-view').hidden=false;},400);}catch(err){msg.textContent=err.message;msg.className='form-message error';}});

  async function loadAuditLogs() {
    const host=$('admin-audit-logs');
    if(!host||!isAdmin)return;
    host.innerHTML='<div class="loading-block">불러오는 중...</div>';
    try{
      const d=await api('/api/admin/audit_logs?limit=50');
      const logs=d.logs||[];
      host.innerHTML=logs.length?logs.map(log=>{const stamp=String(log.created_at||'').replace('T',' ').slice(0,16);return `<div class="admin-audit-item"><div><strong>${esc(log.action)}</strong><span>${esc(log.actor_userid||'관리자')} · ${esc(log.details||'')}</span></div><time>${esc(stamp)}</time></div>`;}).join(''):'<div class="admin-empty-state">기록이 없습니다.</div>';
    }catch(err){host.innerHTML=`<div class="admin-empty-state">${esc(err.message)}</div>`;}
  }

  function loadAdminPanel() {
    const host = $('admin-user-search-results');
    if (host && !host.dataset.ready) {
      host.innerHTML = '<div class="admin-empty-state">이름을 입력해 계정을 조회하세요.</div>';
      host.dataset.ready = '1';
    }
    loadAuditLogs();
  }
  $('admin-audit-refresh')?.addEventListener('click',loadAuditLogs);

  $('admin-user-search-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    const host = $('admin-user-search-results');
    const name = $('admin-user-search-name').value.trim();
    if (!name) return;
    host.innerHTML = '<div class="loading-block">조회 중...</div>';
    try {
      const d = await api(`/api/admin/users?name=${encodeURIComponent(name)}`);
      const users = d.users || [];
      if (!users.length) {
        host.innerHTML = '<div class="admin-empty-state">검색 결과가 없습니다.</div>';
        return;
      }
      host.innerHTML = users.map(u => {
        const role = u.is_admin ? '관리자' : (u.is_teacher ? '선생님' : '일반');
        const posts = (u.posts || []).length
          ? `<div class="admin-user-posts">${u.posts.map(p => `<a href="${esc(p.url)}"><strong>${esc(p.title)}</strong><span>${esc(p.board_name)} · ${esc(String(p.created_at || '').slice(0,10))}</span></a>`).join('')}</div>`
          : '<div class="admin-user-no-posts">작성한 글이 없습니다.</div>';
        const resetButton=u.is_admin?'':`<button class="secondary-button admin-reset-password" type="button" data-user-id="${Number(u.id)}">임시 비밀번호 발급</button>`;
        return `<article class="admin-user-result" data-user-id="${Number(u.id)}"><div class="admin-user-head"><div><strong>${esc(u.name)}</strong><span>${esc(u.student_no || '학번 미등록')}</span></div><span class="admin-role-badge ${u.is_teacher?'teacher':''}">${role}</span></div>${resetButton}<div class="admin-temp-password" hidden></div>${posts}</article>`;
      }).join('');
      host.querySelectorAll('.admin-reset-password').forEach(button=>button.addEventListener('click',async()=>{
        if(!confirm('이 계정의 기존 비밀번호를 사용할 수 없게 하고 임시 비밀번호를 발급할까요?'))return;
        button.disabled=true;
        const article=button.closest('.admin-user-result'),box=article?.querySelector('.admin-temp-password');
        try{
          const d=await api(`/api/admin/users/${button.dataset.userId}/reset_password`,{method:'POST'});
          if(box){box.hidden=false;box.innerHTML=`<span>임시 비밀번호</span><code>${esc(d.temporary_password)}</code><button type="button" class="text-button copy-temp-password">복사</button>`;box.querySelector('.copy-temp-password')?.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(d.temporary_password);}catch(_){}});}
          loadAuditLogs();
        }catch(err){alert(err.message);}finally{button.disabled=false;}
      }));
    } catch (err) {
      host.innerHTML = `<div class="admin-empty-state">${esc(err.message)}</div>`;
    }
  });

  async function setTeacherRole(makeTeacher) {
    const input = $('admin-teacher-student-no');
    const msg = $('admin-teacher-message');
    const studentNo = input?.value.trim() || '';
    try {
      const d = await api('/api/admin/teacher_role', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({student_no: studentNo, is_teacher: makeTeacher})
      });
      msg.textContent = d.message;
      msg.className = 'form-message success';
      const searchName = $('admin-user-search-name')?.value.trim();
      if (searchName) $('admin-user-search-form')?.requestSubmit();
      loadAuditLogs();
    } catch (err) {
      msg.textContent = err.message;
      msg.className = 'form-message error';
    }
  }
  $('admin-teacher-set')?.addEventListener('click', () => setTeacherRole(true));
  $('admin-teacher-unset')?.addEventListener('click', () => setTeacherRole(false));

  function setClassOptions(select, grade, value='1'){ if(!select)return;const CLASS_COUNTS={1:10,2:9,3:10};const max=CLASS_COUNTS[Number(grade)]||1;select.innerHTML=Array.from({length:max},(_,i)=>`<option value="${i+1}">${i+1}반</option>`).join('');select.value=String(Math.min(max,Number(value)||1)); }
  async function openTimetableSettings(){ if(!authenticated){location.href='/login';return;} $('timetable-settings-overlay').hidden=false; const gradeSel=$('timetable-profile-grade'), classSel=$('timetable-profile-classroom'), msg=$('timetable-settings-message');msg.textContent=''; try{const d=await api('/api/timetable_profile'); const p=d.profile||d.suggested||{grade:1,classroom:1};gradeSel.value=String(p.grade);setClassOptions(classSel,p.grade,p.classroom);await renderElectiveSettings(Number(p.grade));}catch(e){msg.textContent=e.message;msg.className='form-message error';}}
  $('timetable-settings-btn')?.addEventListener('click',openTimetableSettings);
  $('timetable-profile-grade')?.addEventListener('change',e=>{setClassOptions($('timetable-profile-classroom'),e.target.value);renderElectiveSettings(Number(e.target.value));});
  async function renderElectiveSettings(grade){const g1=$('grade1-custom-notice'),g2=$('grade2-elective-settings'),editor=$('elective-editor');g1.hidden=grade!==1;g2.hidden=grade!==2;if(grade!==2)return;let saved={};try{const d=await api('/api/custom_timetable');(d.cells||[]).forEach(c=>saved[`${c.day}:${c.period}`]=c.subject);}catch(_){} editor.innerHTML=[...ELECTIVE_SLOTS].sort().map(key=>{const [day,period]=key.split(':').map(Number);const opts=[['humanities','문과 계열'],['science','이과 계열']].map(([k,label])=>`<optgroup label="${label}">${SUBJECT_GROUPS[k].map(s=>`<option value="${esc(s)}" ${saved[key]===s?'selected':''}>${esc(s)}</option>`).join('')}</optgroup>`).join('');return `<label><span>${DAYS[day]} ${period}교시</span><select data-day="${day}" data-period="${period}"><option value="">선택 안 함</option>${opts}</select></label>`;}).join(''); }
  $('timetable-settings-save-btn')?.addEventListener('click',async()=>{const grade=Number($('timetable-profile-grade').value),classroom=Number($('timetable-profile-classroom').value),msg=$('timetable-settings-message');try{await api('/api/timetable_profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({grade,classroom})});if(grade===2){const cells=[...$('elective-editor').querySelectorAll('select')].map(s=>({day:Number(s.dataset.day),period:Number(s.dataset.period),subject:s.value}));await api('/api/custom_timetable',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cells})});}msg.textContent='시간표 설정을 저장했습니다.';msg.className='form-message success';cache.timetable=null;setTimeout(()=>{$('timetable-settings-overlay').hidden=true;loadTimetable();},400);}catch(e){msg.textContent=e.message;msg.className='form-message error';}});

  if(isAdmin){const ag=$('admin-base-grade'),ac=$('admin-base-classroom');setClassOptions(ac,1);ag?.addEventListener('change',()=>setClassOptions(ac,ag.value));$('admin-base-timetable-btn')?.addEventListener('click',()=>{$('admin-base-overlay').hidden=false;loadAdminBase();});$('admin-base-load')?.addEventListener('click',loadAdminBase);async function loadAdminBase(){const grade=Number(ag.value),cl=Number(ac.value),host=$('admin-base-editor'),msg=$('admin-base-message');msg.textContent='';try{const d=await api(`/api/admin/base_timetable?grade=${grade}&classroom=${cl}`),saved={};(d.cells||[]).forEach(c=>saved[`${c.day}:${c.period}`]=c.subject);host.innerHTML=`<div class="admin-grid-head"><span>교시</span>${DAYS.map(x=>`<span>${x}</span>`).join('')}</div>${Array.from({length:7},(_,i)=>i+1).map(p=>`<div class="admin-grid-row"><strong>${p}</strong>${DAYS.map((_,day)=>{const active=p<=DAILY_PERIODS[grade][day];if(!active)return '<span class="admin-inactive">—</span>';const elective=grade===2&&ELECTIVE_SLOTS.has(`${day}:${p}`);return `<label class="${elective?'elective':''}"><input data-day="${day}" data-period="${p}" maxlength="40" value="${esc(saved[`${day}:${p}`]||'')}" placeholder="${elective?'선택과목 교시':'과목'}"></label>`;}).join('')}</div>`).join('')}`;}catch(e){host.innerHTML='';msg.textContent=e.message;msg.className='form-message error';}}
    $('admin-base-save-btn')?.addEventListener('click',async()=>{const cells=[...$('admin-base-editor').querySelectorAll('input')].map(i=>({day:Number(i.dataset.day),period:Number(i.dataset.period),subject:i.value.trim()}));const msg=$('admin-base-message');try{const d=await api('/api/admin/base_timetable',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({grade:Number(ag.value),classroom:Number(ac.value),cells})});msg.textContent=d.message;msg.className='form-message success';cache.timetable=null;loadAuditLogs();}catch(e){msg.textContent=e.message;msg.className='form-message error';}});}

  window.addEventListener('pageshow',e=>{if(e.persisted&&authenticated)loadBoards();});

  document.querySelectorAll('[data-close-modal]').forEach(btn=>btn.addEventListener('click',()=>{$(btn.dataset.closeModal).hidden=true;}));
  document.querySelectorAll('.portal-modal-overlay').forEach(overlay=>overlay.addEventListener('click',e=>{if(e.target===overlay)overlay.hidden=true;}));

  loadMeals(); loadWeather(); loadTimetable();
});
