(function() {
    /* --- DOM 요소 --- */
    const timetableContainer = document.getElementById('timetable-data-container');
    const timetableLoading = document.getElementById('timetable-loading');

    // 제목 부분의 새로운 input 요소
    const titleGradeInput = document.getElementById('title-grade-input');
    const titleClassInput = document.getElementById('title-class-input');
    const titleDateInput = document.getElementById('title-date-input');

    const mealContent = document.getElementById('meal-content');
    const mealLoading = document.getElementById('meal-loading');
    const mealDateDisplay = document.getElementById('meal-date-display');
    const myClassesList = document.getElementById('my-classes-list'); // 추가

    // 개인 시간표 UI
    const schoolTimetableTab = document.getElementById('school-timetable-tab');
    const personalTimetableTab = document.getElementById('personal-timetable-tab');
    const personalTimetableContainer = document.getElementById('personal-timetable-container');
    const timetableChangeAlert = document.getElementById('timetable-change-alert');
    const timetableSettingsBtn = document.getElementById('timetable-settings-btn');
    const timetableSettingsOverlay = document.getElementById('timetable-settings-overlay');
    const timetableSettingsCloseBtn = document.getElementById('timetable-settings-close-btn');
    const timetableSettingsCancelBtn = document.getElementById('timetable-settings-cancel-btn');
    const timetableSettingsSaveBtn = document.getElementById('timetable-settings-save-btn');
    const timetableProfileGrade = document.getElementById('timetable-profile-grade');
    const timetableProfileClassroom = document.getElementById('timetable-profile-classroom');
    const grade2ElectiveSettings = document.getElementById('grade2-elective-settings');
    const grade1CustomNotice = document.getElementById('grade1-custom-notice');
    const electiveEditor = document.getElementById('elective-editor');

    const adminBaseTimetableBtn = document.getElementById('admin-base-timetable-btn');
    const adminBaseOverlay = document.getElementById('admin-base-overlay');
    const adminBaseCloseBtn = document.getElementById('admin-base-close-btn');
    const adminBaseCancelBtn = document.getElementById('admin-base-cancel-btn');
    const adminBaseSaveBtn = document.getElementById('admin-base-save-btn');
    const adminBaseEditor = document.getElementById('admin-base-editor');
    const adminBaseSubtitle = document.getElementById('admin-base-subtitle');

    const isAuthenticated = document.body.dataset.authenticated === '1';
    const isAdmin = document.body.dataset.isAdmin === '1';

    // 한 페이지 안에서 같은 날짜/학급으로 다시 이동했을 때 서버 재요청도 피합니다.
    const mealMemoryCache = new Map();
    const timetableMemoryCache = new Map();

    /* --- 내 클래스 목록 로드 및 렌더링 --- */
    async function loadMyClasses() {
        myClassesList.innerHTML = ''; // 기존 목록 비우기
        try {
            const response = await fetch('/api/my_classes');
            const data = await response.json();

            if (data.success && data.classes.length > 0) {
                data.classes.forEach(cls => {
                    const listItem = document.createElement('li');
                    listItem.dataset.grade = cls.grade;
                    listItem.dataset.classroom = cls.classroom;
                    listItem.classList.add('my-class-item');

                    listItem.innerHTML = `
                        <span class="class-info">${cls.display_name}</span>
                    `;

                    // 클래스 정보 클릭 시 페이지 이동
                    listItem.querySelector('.class-info').addEventListener('click', () => {
                        window.location.href = `/class/${cls.grade}/${cls.classroom}`;
                    });

                    myClassesList.appendChild(listItem);
                });
            } else if (data.success && data.classes.length === 0) {
                myClassesList.innerHTML = '<li style="color:#ccc; padding:8px 0;">추가된 클래스가 없습니다.</li>';
            } else {
                // API 호출은 성공했으나, success: false인 경우 (예: 서버 내부 오류)
                console.error('Error loading my classes from API:', data.message);
                myClassesList.innerHTML = '<li style="color:red; padding:8px 0;">클래스 로드 중 오류 발생</li>';
            }
        } catch (error) {
            console.error('Error loading my classes:', error);
            myClassesList.innerHTML = '<li style="color:red; padding:8px 0;">클래스 로드 중 오류 발생</li>';
        }
    }

    /* --- 프로필 드롭다운 --- */
    const profile = document.querySelector('.profile-mini');
    if (profile) {
        const btn = profile.querySelector('.dots-btn');
        const dropdown = profile.querySelector('.profile-dropdown');
        const closeDropdown = () => dropdown?.setAttribute('aria-hidden', 'true');
        const openDropdown = () => dropdown?.setAttribute('aria-hidden', 'false');

        document.addEventListener('click', (e) => !profile.contains(e.target) && closeDropdown());
        btn?.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = dropdown.getAttribute('aria-hidden') === 'false';
            isOpen ? closeDropdown() : openDropdown();
        });
        document.addEventListener('keydown', (e) => e.key === 'Escape' && closeDropdown());
    }

    /* --- 데이터 렌더링 함수 --- */    function renderTimetable(timetableData) {
        if (!timetableData || timetableData.length === 0) {
            timetableContainer.innerHTML = '<p class="placeholder">해당 기간에 시간표 정보가 없습니다.</p>';
            return;
        }

        let timetableHtml = '';
        timetableData.forEach(dayData => {
            const d = new Date(dayData.date.substring(0, 4), dayData.date.substring(4, 6) - 1, dayData.date.substring(6, 8));
            const dayNames = ["일", "월", "화", "수", "목", "금", "토"];
            const dayOfWeek = dayNames[d.getDay()];
            const displayDate = `${d.getMonth() + 1}월 ${d.getDate()}일 (${dayOfWeek})`;

            timetableHtml += `<div class="day-box"><h4>${displayDate}</h4><ul class="timetable-list">`;
            if (dayData.timetable.length > 0) {
                dayData.timetable.forEach((subject, index) => {
                    timetableHtml += `<li><span class="period">${index + 1}교시</span> ${subject}</li>`;
                });
            } else {
                timetableHtml += `<li class="no-data">수업 없음</li>`;
            }
            timetableHtml += `</ul></div>`;
        });

        timetableContainer.innerHTML = timetableHtml;
    }

    function renderMeal(mealData) {
        if (!mealData || mealData.length === 0) {
            mealContent.innerHTML = '<p class="placeholder">급식 정보가 없습니다.</p>';
            return;
        }

        let mealHtml = '';
        mealData.forEach(meal => {
            const menuHtml = meal.menu.replace(/\n/g, '<br>');
            mealHtml += `<div class="meal-item"><h4> ${meal.time}</h4><div>${menuHtml}</div></div>`;
        });
        mealContent.innerHTML = mealHtml;
    }

    /* --- API 호출 함수 --- */
    async function fetchMeal(date) {
        if (mealMemoryCache.has(date)) return mealMemoryCache.get(date);

        const url = `/api/data?date=${date}&data_type=meal`;
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            const meal = data.meal || [];
            mealMemoryCache.set(date, meal);
            return meal;
        } catch (error) {
            console.error('Error fetching meal:', error);
            return [];
        }
    }

    async function fetchTimetable(date, grade, classroom) {
        const cacheKey = `${date}:${grade}:${classroom}`;
        if (timetableMemoryCache.has(cacheKey)) return timetableMemoryCache.get(cacheKey);

        const url = `/api/data?date=${date}&grade=${grade}&classroom=${classroom}&data_type=timetable`;
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            const timetable = data.timetable || [];
            timetableMemoryCache.set(cacheKey, timetable);
            return timetable;
        } catch (error) {
            console.error('Error fetching timetable:', error);
            return [];
        }
    }

    async function fetchMealAndTimetable(date, grade, classroom) {
        const timetableKey = `${date}:${grade}:${classroom}`;
        const url = `/api/data?date=${date}&grade=${grade}&classroom=${classroom}&data_type=all`;
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            const meal = data.meal || [];
            const timetable = data.timetable || [];
            mealMemoryCache.set(date, meal);
            timetableMemoryCache.set(timetableKey, timetable);
            return { meal, timetable };
        } catch (error) {
            console.error('Error fetching combined data:', error);
            return { meal: [], timetable: [] };
        }
    }

    // Variables to store last fetched values
    let lastFetchedDate = '';
    let lastFetchedGrade = '';
    let lastFetchedClassroom = '';

    /* --- 데이터 로드 및 렌더링 총괄 --- */
    async function loadAndRenderData(date, grade, classroom) {
        // 학년에 따라 반의 최댓값 동적 변경
        const newMaxClass = (parseInt(grade, 10) === 2) ? 10 : 9;
        titleClassInput.setAttribute('max', newMaxClass);

        // 현재 반이 새로운 최댓값을 초과하면 조정
        if (parseInt(classroom, 10) > newMaxClass) {
            classroom = newMaxClass.toString();
        }

        // input 값을 현재 값으로 설정
        const formattedDate = `${date.substring(0, 4)}-${date.substring(4, 6)}-${date.substring(6, 8)}`;
        titleDateInput.value = formattedDate;
        titleGradeInput.value = grade;
        titleClassInput.value = classroom;

        // 어떤 데이터를 가져와야 하는지 결정
        let shouldFetchMeal = (date !== lastFetchedDate);
        let shouldFetchTimetable = (date !== lastFetchedDate || grade !== lastFetchedGrade || classroom !== lastFetchedClassroom);

        // 로딩 인디케이터 표시 (필요한 경우에만)
        if (mealLoading && shouldFetchMeal) {
            mealLoading.style.display = 'inline';
        }
        if (timetableLoading && shouldFetchTimetable) {
            timetableLoading.style.visibility = 'visible'; // FIX: Use visibility
        }

        // A promise that resolves after a minimum delay
        // const minDelay = (duration) => new Promise(resolve => setTimeout(resolve, duration));

        // 급식 + 시간표가 동시에 필요한 경우 서버 요청 1회로 합칩니다.
        if (shouldFetchMeal && shouldFetchTimetable && mealContent && timetableContainer) {
            if (mealDateDisplay) {
                const month = parseInt(date.substring(4, 6), 10);
                const day = parseInt(date.substring(6, 8), 10);
                mealDateDisplay.textContent = `${month}월 ${day}일 급식`;
            }

            const timetableKey = `${date}:${grade}:${classroom}`;
            let mealData;
            let timetableData;

            // 이미 페이지 메모리 캐시에 둘 다 있으면 네트워크 요청 없이 사용합니다.
            if (mealMemoryCache.has(date) && timetableMemoryCache.has(timetableKey)) {
                mealData = mealMemoryCache.get(date);
                timetableData = timetableMemoryCache.get(timetableKey);
            } else if (!mealMemoryCache.has(date) && !timetableMemoryCache.has(timetableKey)) {
                const combined = await fetchMealAndTimetable(date, grade, classroom);
                mealData = combined.meal;
                timetableData = combined.timetable;
            } else {
                // 둘 중 하나만 캐시에 있는 드문 경우에는 없는 데이터만 개별 요청합니다.
                mealData = mealMemoryCache.has(date) ? mealMemoryCache.get(date) : await fetchMeal(date);
                timetableData = timetableMemoryCache.has(timetableKey)
                    ? timetableMemoryCache.get(timetableKey)
                    : await fetchTimetable(date, grade, classroom);
            }

            mealContent.innerHTML = '';
            timetableContainer.innerHTML = '';
            renderMeal(mealData);
            renderTimetable(timetableData);
            if (mealLoading) mealLoading.style.display = 'none';
            if (timetableLoading) timetableLoading.style.visibility = 'hidden';

            lastFetchedDate = date;
            lastFetchedGrade = grade;
            lastFetchedClassroom = classroom;
        } else {
            // 급식만 필요한 경우
            if (shouldFetchMeal && mealContent) {
                if (mealDateDisplay) {
                    const month = parseInt(date.substring(4, 6), 10);
                    const day = parseInt(date.substring(6, 8), 10);
                    mealDateDisplay.textContent = `${month}월 ${day}일 급식`;
                }

                const mealData = await fetchMeal(date);
                mealContent.innerHTML = '';
                renderMeal(mealData);
                if (mealLoading) mealLoading.style.display = 'none';
                lastFetchedDate = date;
            }

            // 시간표만 필요한 경우
            if (shouldFetchTimetable && timetableContainer) {
                const timetableData = await fetchTimetable(date, grade, classroom);
                timetableContainer.innerHTML = '';
                renderTimetable(timetableData);
                if (timetableLoading) timetableLoading.style.visibility = 'hidden';
                lastFetchedDate = date;
                lastFetchedGrade = grade;
                lastFetchedClassroom = classroom;
            }
        }

        // 만약 아무것도 가져오지 않았다면 로딩 인디케이터를 숨김 (초기 로드 시 등)
        if (mealLoading && !shouldFetchMeal) {
            mealLoading.style.display = 'none';
        }
        if (timetableLoading && !shouldFetchTimetable) {
            timetableLoading.style.visibility = 'hidden'; // FIX: Use visibility
        }
    }


    /* --- 개인 시간표 / 반 등록 / 선택과목 --- */
    const WEEKDAY_NAMES = ['월', '화', '수', '목', '금'];
    const DAILY_PERIODS = {
        1: [7, 7, 6, 7, 7],
        2: [7, 7, 6, 7, 5]
    };
    const ELECTIVE_SLOTS = new Set([
        '0:1', '0:2', '0:5', '0:6',
        '1:2', '1:5',
        '2:2', '2:3', '2:5',
        '3:1', '3:2', '3:3',
        '4:1', '4:2', '4:4'
    ]);
    const ELECTIVE_GROUPS = {
        humanities: ['윤리와 사상', '법과 사회', '한국지리 탐구', '경제', '일본어 회화', '사회 문제 탐구', '동아시아 역사 기행'],
        science: ['역학과 에너지', '물질과 에너지', '세포와 물질대사', '지구시스템과학', '융합과학 탐구', '인공지능 기초', '지식 재산 일반', '인공지능 수학']
    };

    let currentTimetableView = 'school';
    let timetableProfile = null;
    let timetableProfileSuggestion = null;
    let savedElectives = [];
    let lastPersonalDate = '';

    function isActivePeriod(grade, day, period) {
        const daily = DAILY_PERIODS[Number(grade)];
        return Boolean(daily && daily[day] && period <= daily[day]);
    }

    function electiveCellAt(cells, day, period) {
        return (cells || []).find(cell => Number(cell.day) === day && Number(cell.period) === period) || null;
    }

    function updateClassroomOptions(grade, preferredValue = null) {
        if (!timetableProfileClassroom) return;
        const maxClass = Number(grade) === 2 ? 10 : 9;
        const oldValue = preferredValue || timetableProfileClassroom.value || '1';
        timetableProfileClassroom.replaceChildren();
        for (let classroom = 1; classroom <= maxClass; classroom += 1) {
            const option = document.createElement('option');
            option.value = String(classroom);
            option.textContent = `${classroom}반`;
            timetableProfileClassroom.appendChild(option);
        }
        const normalized = Math.min(maxClass, Math.max(1, Number(oldValue) || 1));
        timetableProfileClassroom.value = String(normalized);
    }

    function makeElectiveSelect(day, period, selectedSubject = '') {
        const select = document.createElement('select');
        select.className = 'elective-subject-select';
        select.dataset.day = String(day);
        select.dataset.period = String(period);
        select.setAttribute('aria-label', `${WEEKDAY_NAMES[day]}요일 ${period}교시 선택과목`);

        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = '선택 안 함';
        select.appendChild(empty);

        const groups = [
            ['humanities', '문과 계열'],
            ['science', '이과 계열']
        ];
        groups.forEach(([key, label]) => {
            const optgroup = document.createElement('optgroup');
            optgroup.label = label;
            ELECTIVE_GROUPS[key].forEach(subject => {
                const option = document.createElement('option');
                option.value = subject;
                option.textContent = subject;
                option.selected = subject === selectedSubject;
                optgroup.appendChild(option);
            });
            select.appendChild(optgroup);
        });
        return select;
    }

    function renderElectiveEditor(cells = savedElectives) {
        if (!electiveEditor) return;
        const wrap = document.createElement('div');
        wrap.className = 'custom-timetable-editor-wrap';
        const table = document.createElement('table');
        table.className = 'custom-editor-table elective-editor-table';

        const thead = document.createElement('thead');
        const trh = document.createElement('tr');
        const periodHead = document.createElement('th');
        periodHead.textContent = '교시';
        trh.appendChild(periodHead);
        WEEKDAY_NAMES.forEach(dayName => {
            const th = document.createElement('th');
            th.textContent = dayName;
            trh.appendChild(th);
        });
        thead.appendChild(trh);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        for (let period = 1; period <= 7; period += 1) {
            const row = document.createElement('tr');
            const periodCell = document.createElement('td');
            periodCell.className = 'period-cell';
            periodCell.textContent = `${period}교시`;
            row.appendChild(periodCell);

            for (let day = 0; day < 5; day += 1) {
                const td = document.createElement('td');
                if (!isActivePeriod(2, day, period)) {
                    td.className = 'editor-disabled-cell';
                    td.textContent = '—';
                } else if (ELECTIVE_SLOTS.has(`${day}:${period}`)) {
                    const existing = electiveCellAt(cells, day, period);
                    td.className = 'editor-elective-cell';
                    td.appendChild(makeElectiveSelect(day, period, existing?.subject || ''));
                } else {
                    td.className = 'editor-common-cell';
                    td.textContent = '공통과목';
                }
                row.appendChild(td);
            }
            tbody.appendChild(row);
        }
        table.appendChild(tbody);
        wrap.appendChild(table);
        electiveEditor.replaceChildren(wrap);
    }

    function collectElectiveSettings() {
        if (!electiveEditor) return [];
        return Array.from(electiveEditor.querySelectorAll('.elective-subject-select')).map(select => ({
            day: Number(select.dataset.day),
            period: Number(select.dataset.period),
            subject: select.value
        }));
    }

    function showTimetableAlert(alerts, baselineConfigured) {
        if (!timetableChangeAlert) return;
        if (!baselineConfigured) {
            timetableChangeAlert.hidden = false;
            timetableChangeAlert.className = 'timetable-change-alert info';
            timetableChangeAlert.innerHTML = '<strong>기준 시간표 미설정</strong><span>관리자가 이 반의 본래 시간표를 저장하면 이후 변경된 공통과목을 감지할 수 있습니다.</span>';
            return;
        }
        if (!alerts || alerts.length === 0) {
            timetableChangeAlert.hidden = true;
            timetableChangeAlert.innerHTML = '';
            return;
        }

        const details = alerts.map(item => `${item.day_name} ${item.period}교시: ${escapeHtml(item.from)} → ${escapeHtml(item.to)}`).join(' · ');
        timetableChangeAlert.hidden = false;
        timetableChangeAlert.className = 'timetable-change-alert warning';
        timetableChangeAlert.innerHTML = `<strong>시간표 변경 ${alerts.length}건</strong><span>${details}</span>`;
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }

    function renderPersonalTimetable(data) {
        if (!personalTimetableContainer) return;
        if (!data?.success) {
            personalTimetableContainer.innerHTML = `<p class="placeholder">${escapeHtml(data?.message || '개인 시간표를 불러올 수 없습니다.')}</p>`;
            return;
        }

        const wrap = document.createElement('div');
        wrap.className = 'custom-timetable-wrap personal-timetable-wrap';

        const meta = document.createElement('div');
        meta.className = 'personal-timetable-meta';
        meta.innerHTML = `<strong>${data.profile.grade}학년 ${data.profile.classroom}반</strong><span>${data.profile.grade === 2 ? '선택과목이 반영된 개인 시간표' : '기준 시간표 변경 감지 시간표'}</span>`;
        wrap.appendChild(meta);

        const table = document.createElement('table');
        table.className = 'custom-timetable-table personal-timetable-table';
        const thead = document.createElement('thead');
        const headRow = document.createElement('tr');
        const firstHead = document.createElement('th');
        firstHead.className = 'period-head';
        firstHead.textContent = '교시';
        headRow.appendChild(firstHead);
        data.days.forEach(day => {
            const th = document.createElement('th');
            const date = String(day.date);
            th.innerHTML = `${day.day_name}<small>${Number(date.slice(4, 6))}/${Number(date.slice(6, 8))}</small>`;
            headRow.appendChild(th);
        });
        thead.appendChild(headRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        for (let period = 1; period <= 7; period += 1) {
            const row = document.createElement('tr');
            const periodCell = document.createElement('td');
            periodCell.className = 'period-cell';
            periodCell.textContent = `${period}교시`;
            row.appendChild(periodCell);

            data.days.forEach(day => {
                const cell = day.cells.find(item => Number(item.period) === period);
                const td = document.createElement('td');
                if (!cell || !cell.active) {
                    td.className = 'custom-subject-cell inactive';
                    td.textContent = '—';
                } else {
                    td.className = 'custom-subject-cell';
                    if (cell.elective) td.classList.add('elective');
                    if (cell.changed) td.classList.add('changed');
                    td.textContent = cell.subject || '—';
                    if (cell.changed) {
                        const badge = document.createElement('span');
                        badge.className = 'changed-badge';
                        badge.textContent = '변경';
                        td.appendChild(badge);
                        td.title = `기준: ${cell.base_subject || '없음'} / 현재: ${cell.actual_subject || '없음'}`;
                    }
                }
                row.appendChild(td);
            });
            tbody.appendChild(row);
        }
        table.appendChild(tbody);
        wrap.appendChild(table);
        personalTimetableContainer.replaceChildren(wrap);
        showTimetableAlert(data.alerts || [], data.baseline_configured);
    }

    async function loadPersonalTimetable(date = titleDateInput?.value?.replaceAll('-', '') || '') {
        if (!personalTimetableContainer) return;
        if (!isAuthenticated) {
            personalTimetableContainer.innerHTML = '<p class="placeholder">로그인 후 반을 등록하면 내 시간표를 사용할 수 있습니다.</p>';
            if (timetableChangeAlert) timetableChangeAlert.hidden = true;
            return;
        }
        personalTimetableContainer.innerHTML = '<p class="placeholder">내 시간표를 불러오는 중...</p>';
        try {
            const response = await fetch(`/api/personal_timetable?date=${encodeURIComponent(date)}`, { cache: 'no-store' });
            const data = await response.json().catch(() => ({}));
            if (response.status === 409 && data.needs_registration) {
                timetableProfile = null;
                personalTimetableContainer.innerHTML = '<div class="personal-empty-state"><strong>반 등록이 필요합니다.</strong><span>시간표 설정에서 학년과 반을 한 번 등록해주세요.</span></div>';
                if (timetableChangeAlert) timetableChangeAlert.hidden = true;
                return;
            }
            if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
            timetableProfile = data.profile;
            lastPersonalDate = date;
            renderPersonalTimetable(data);
        } catch (error) {
            console.error('Error loading personal timetable:', error);
            personalTimetableContainer.innerHTML = `<p class="placeholder">${escapeHtml(error.message || '내 시간표를 불러오지 못했습니다.')}</p>`;
        }
    }

    function setTimetableView(view) {
        currentTimetableView = view;
        const personal = view === 'personal';
        schoolTimetableTab?.classList.toggle('active', !personal);
        personalTimetableTab?.classList.toggle('active', personal);
        if (timetableContainer) timetableContainer.hidden = personal;
        if (personalTimetableContainer) personalTimetableContainer.hidden = !personal;
        if (timetableChangeAlert && !personal) timetableChangeAlert.hidden = true;
    }

    async function loadProfileSettings() {
        const response = await fetch('/api/timetable_profile', { cache: 'no-store' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
        timetableProfile = data.profile || null;
        timetableProfileSuggestion = data.suggested || null;
        return data;
    }

    async function loadSavedElectives() {
        if (!timetableProfile || Number(timetableProfile.grade) !== 2) {
            savedElectives = [];
            return;
        }
        const response = await fetch('/api/custom_timetable', { cache: 'no-store' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
        savedElectives = data.cells || [];
    }

    function updateSettingsGradeUI() {
        const grade = Number(timetableProfileGrade?.value || 1);
        updateClassroomOptions(grade);
        if (grade2ElectiveSettings) grade2ElectiveSettings.hidden = grade !== 2;
        if (grade1CustomNotice) grade1CustomNotice.hidden = grade !== 1;
        if (grade === 2) renderElectiveEditor(savedElectives);
    }

    async function openTimetableSettings() {
        if (!isAuthenticated) {
            alert('로그인 후 시간표 설정을 사용할 수 있습니다.');
            return;
        }
        try {
            await loadProfileSettings();
            const seed = timetableProfile || timetableProfileSuggestion || { grade: 1, classroom: 1 };
            timetableProfileGrade.value = String(seed.grade);
            updateClassroomOptions(seed.grade, seed.classroom);
            if (Number(seed.grade) === 2 && timetableProfile) {
                await loadSavedElectives();
            } else {
                savedElectives = [];
            }
            updateSettingsGradeUI();
            if (timetableSettingsOverlay) timetableSettingsOverlay.style.display = 'flex';
        } catch (error) {
            console.error('Error opening timetable settings:', error);
            alert(`시간표 설정을 불러오지 못했습니다: ${error.message}`);
        }
    }

    function closeTimetableSettings() {
        if (timetableSettingsOverlay) timetableSettingsOverlay.style.display = 'none';
    }

    async function saveTimetableSettings() {
        const grade = Number(timetableProfileGrade?.value || 0);
        const classroom = Number(timetableProfileClassroom?.value || 0);
        const profileResponse = await fetch('/api/timetable_profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ grade, classroom })
        });
        const profileData = await profileResponse.json().catch(() => ({}));
        if (!profileResponse.ok || !profileData.success) {
            throw new Error(profileData.message || `HTTP ${profileResponse.status}`);
        }
        timetableProfile = profileData.profile;

        if (grade === 2) {
            const cells = collectElectiveSettings();
            const electiveResponse = await fetch('/api/custom_timetable', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cells })
            });
            const electiveData = await electiveResponse.json().catch(() => ({}));
            if (!electiveResponse.ok || !electiveData.success) {
                throw new Error(electiveData.message || `HTTP ${electiveResponse.status}`);
            }
            savedElectives = cells;
        } else {
            savedElectives = [];
        }
    }

    function renderAdminBaseEditor(grade, cells) {
        if (!adminBaseEditor) return;
        const map = new Map((cells || []).map(cell => [`${cell.day}:${cell.period}`, cell.subject || '']));
        const wrap = document.createElement('div');
        wrap.className = 'custom-timetable-editor-wrap';
        const table = document.createElement('table');
        table.className = 'custom-editor-table admin-base-editor-table';

        const thead = document.createElement('thead');
        const trh = document.createElement('tr');
        const blank = document.createElement('th');
        blank.textContent = '교시';
        trh.appendChild(blank);
        WEEKDAY_NAMES.forEach(dayName => {
            const th = document.createElement('th');
            th.textContent = dayName;
            trh.appendChild(th);
        });
        thead.appendChild(trh);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        for (let period = 1; period <= 7; period += 1) {
            const row = document.createElement('tr');
            const pc = document.createElement('td');
            pc.className = 'period-cell';
            pc.textContent = `${period}교시`;
            row.appendChild(pc);
            for (let day = 0; day < 5; day += 1) {
                const td = document.createElement('td');
                if (!isActivePeriod(grade, day, period)) {
                    td.className = 'editor-disabled-cell';
                    td.textContent = '—';
                } else {
                    const input = document.createElement('input');
                    input.type = 'text';
                    input.maxLength = 40;
                    input.value = map.get(`${day}:${period}`) || '';
                    input.placeholder = Number(grade) === 2 && ELECTIVE_SLOTS.has(`${day}:${period}`) ? '선택과목 교시' : '과목명';
                    input.dataset.day = String(day);
                    input.dataset.period = String(period);
                    input.className = 'base-subject-input';
                    td.appendChild(input);
                }
                row.appendChild(td);
            }
            tbody.appendChild(row);
        }
        table.appendChild(tbody);
        wrap.appendChild(table);
        adminBaseEditor.replaceChildren(wrap);
    }

    function collectAdminBaseCells() {
        if (!adminBaseEditor) return [];
        return Array.from(adminBaseEditor.querySelectorAll('.base-subject-input')).map(input => ({
            day: Number(input.dataset.day),
            period: Number(input.dataset.period),
            subject: input.value.trim()
        }));
    }

    async function openAdminBaseEditor() {
        if (!isAdmin) return;
        const grade = Number(titleGradeInput?.value || 0);
        const classroom = Number(titleClassInput?.value || 0);
        if (![1, 2].includes(grade)) {
            alert('현재 기준 시간표 설정은 1·2학년만 지원합니다.');
            return;
        }
        try {
            const response = await fetch(`/api/admin/base_timetable?grade=${grade}&classroom=${classroom}`, { cache: 'no-store' });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
            if (adminBaseSubtitle) adminBaseSubtitle.textContent = `${grade}학년 ${classroom}반의 본래 시간표를 저장합니다. 공통과목 변경 감지의 기준이 됩니다.`;
            renderAdminBaseEditor(grade, data.cells || []);
            if (adminBaseOverlay) adminBaseOverlay.style.display = 'flex';
        } catch (error) {
            console.error('Error opening base timetable editor:', error);
            alert(`기준 시간표를 불러오지 못했습니다: ${error.message}`);
        }
    }

    function closeAdminBaseEditor() {
        if (adminBaseOverlay) adminBaseOverlay.style.display = 'none';
    }

    function setupPersonalTimetable() {
        schoolTimetableTab?.addEventListener('click', () => setTimetableView('school'));
        personalTimetableTab?.addEventListener('click', async () => {
            setTimetableView('personal');
            await loadPersonalTimetable();
        });
        timetableSettingsBtn?.addEventListener('click', openTimetableSettings);
        timetableProfileGrade?.addEventListener('change', () => {
            const previousClass = timetableProfileClassroom?.value || '1';
            updateClassroomOptions(Number(timetableProfileGrade.value), previousClass);
            savedElectives = Number(timetableProfileGrade.value) === 2 && timetableProfile?.grade === 2 ? savedElectives : [];
            updateSettingsGradeUI();
        });
        timetableSettingsCloseBtn?.addEventListener('click', closeTimetableSettings);
        timetableSettingsCancelBtn?.addEventListener('click', closeTimetableSettings);
        timetableSettingsOverlay?.addEventListener('click', event => {
            if (event.target === timetableSettingsOverlay) closeTimetableSettings();
        });
        timetableSettingsSaveBtn?.addEventListener('click', async () => {
            const original = timetableSettingsSaveBtn.textContent;
            timetableSettingsSaveBtn.disabled = true;
            timetableSettingsSaveBtn.textContent = '저장 중...';
            try {
                await saveTimetableSettings();
                closeTimetableSettings();
                setTimetableView('personal');
                await loadPersonalTimetable();
            } catch (error) {
                console.error('Error saving timetable settings:', error);
                alert(`시간표 설정 저장에 실패했습니다: ${error.message}`);
            } finally {
                timetableSettingsSaveBtn.disabled = false;
                timetableSettingsSaveBtn.textContent = original;
            }
        });

        adminBaseTimetableBtn?.addEventListener('click', openAdminBaseEditor);
        adminBaseCloseBtn?.addEventListener('click', closeAdminBaseEditor);
        adminBaseCancelBtn?.addEventListener('click', closeAdminBaseEditor);
        adminBaseOverlay?.addEventListener('click', event => {
            if (event.target === adminBaseOverlay) closeAdminBaseEditor();
        });
        adminBaseSaveBtn?.addEventListener('click', async () => {
            const grade = Number(titleGradeInput?.value || 0);
            const classroom = Number(titleClassInput?.value || 0);
            const original = adminBaseSaveBtn.textContent;
            adminBaseSaveBtn.disabled = true;
            adminBaseSaveBtn.textContent = '저장 중...';
            try {
                const response = await fetch('/api/admin/base_timetable', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ grade, classroom, cells: collectAdminBaseCells() })
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.success) throw new Error(data.message || `HTTP ${response.status}`);
                closeAdminBaseEditor();
                alert(data.message || '기준 시간표를 저장했습니다.');
                if (currentTimetableView === 'personal') await loadPersonalTimetable();
            } catch (error) {
                console.error('Error saving base timetable:', error);
                alert(`기준 시간표 저장에 실패했습니다: ${error.message}`);
            } finally {
                adminBaseSaveBtn.disabled = false;
                adminBaseSaveBtn.textContent = original;
            }
        });

        document.addEventListener('keydown', event => {
            if (event.key !== 'Escape') return;
            if (timetableSettingsOverlay?.style.display === 'flex') closeTimetableSettings();
            if (adminBaseOverlay?.style.display === 'flex') closeAdminBaseEditor();
        });
    }

    /* --- 유틸리티 함수 --- */
    function debounce(func, delay) {
        let timeout;
        return function(...args) {
            const context = this;
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(context, args), delay);
        };
    }

    // 제목 부분의 input 값이 변경되었을 때 데이터 다시 로드
    function _handleTitleInputChange() {
        // 시각적 동기화 로직 먼저 수행
        const newGrade = titleGradeInput.value;
        let newClass = titleClassInput.value;
        const newMax = (parseInt(newGrade, 10) === 2) ? 10 : 9;
        titleClassInput.setAttribute('max', newMax);
        if (parseInt(newClass, 10) > newMax) {
            newClass = newMax.toString();
            titleClassInput.value = newClass;
        }

        // 데이터 로드
        const date = titleDateInput.value.replaceAll("-", "");
        const grade = titleGradeInput.value;
        const classroom = titleClassInput.value;
        loadAndRenderData(date, grade, classroom);
        if (currentTimetableView === 'personal' && date !== lastPersonalDate) {
            loadPersonalTimetable(date);
        }
    }

    const handleTitleInputChange = debounce(_handleTitleInputChange, 500); // 0.5초 디바운스

    function setupTitleInputs() {
        // 값 변경 시 시각적 동기화 및 데이터 로드
        if (titleDateInput) {
            titleDateInput.addEventListener('change', handleTitleInputChange);
        }

        if (titleGradeInput) {
            titleGradeInput.addEventListener('input', function() {
                const oldValue = this.value;
                let value = parseInt(this.value, 10);
                const min = parseInt(this.min, 10);
                const max = parseInt(this.max, 10);

                if (isNaN(value)) {
                    this.value = min;
                } else if (value < min) {
                    this.value = min;
                } else if (value > max) {
                    this.value = max;
                }
                if (oldValue !== this.value) {
                    handleTitleInputChange();
                }
            });
        }

        if (titleClassInput) {
            titleClassInput.addEventListener('input', function() {
                const oldValue = this.value;
                this.value = this.value.replace(/[^0-9]/g, '');
                const min = parseInt(this.min, 10);
                const max = parseInt(this.max, 10);
                let value = parseInt(this.value, 10);
                if (this.value === '' || isNaN(value)) {
                    this.value = min;
                } else {
                    this.value = Math.max(min, Math.min(value, max));
                }
                if (oldValue !== this.value) {
                    handleTitleInputChange();
                }
            });
        }

        // Mouse wheel event (only visual change, no data load)
        const handleWheel = (e) => {
            e.preventDefault();
            const input = e.target;
            let value = parseInt(input.value, 10);
            const min = parseInt(input.min, 10);
            const max = parseInt(input.max, 10);

            if (e.deltaY < 0) { // 스크롤 업
                value = isNaN(value) ? min : Math.min(max, value + 1);
            } else { // 스크롤 다운
                value = isNaN(value) ? min : Math.max(min, value - 1);
            }
            const oldValue = input.value;
            input.value = value;
            // 휠 이벤트 후에도 데이터 로드
            if (oldValue !== input.value) {
                handleTitleInputChange();
            }
        };

        if (titleGradeInput) {
            titleGradeInput.addEventListener('wheel', handleWheel);
        }
        if (titleClassInput) {
            titleClassInput.addEventListener('wheel', handleWheel);
        }

        // Revised handleSingleDigitInput: now calls handleTitleInputChange if value changes
        function handleSingleDigitInput(e) {
            const min = parseInt(this.min, 10);
            const max = parseInt(this.max, 10);

            // Allow control keys (backspace, delete, tab, arrows, etc.)
            if (['Backspace', 'Delete', 'Tab', 'Escape', 'Enter', 'ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key) ||
                (e.ctrlKey && ['a', 'c', 'v', 'x'].includes(e.key.toLowerCase())) ||
                (e.metaKey && ['a', 'c', 'v', 'x'].includes(e.key.toLowerCase()))) {
                return; // Let these keys work
            }

            // If a digit is typed
            if (e.key.match(/^\d$/)) {
                const typedDigit = parseInt(e.key, 10);

                if (typedDigit >= min && typedDigit <= max) {
                    const oldValue = this.value;
                    this.value = typedDigit;
                    e.preventDefault();
                    if (oldValue !== this.value) {
                        handleTitleInputChange();
                    }
                } else {
                    e.preventDefault();
                }
            } else {
                e.preventDefault();
            }
        }

        // Attach this to both grade and class inputs
        if (titleGradeInput) {
            titleGradeInput.addEventListener('keydown', handleSingleDigitInput);
        }
        if (titleClassInput) {
            titleClassInput.addEventListener('keydown', handleSingleDigitInput);
        }
    }

    // 페이지 로드 시 초기 데이터 로드
    document.addEventListener('DOMContentLoaded', async () => {
        const body = document.body;
        const initialDate = body.dataset.initialDate;
        let initialGrade = body.dataset.initialGrade;
        let initialClassroom = body.dataset.initialClassroom;
        
        // 제목 input에 이벤트 리스너 설정
        setupTitleInputs();
        setupPersonalTimetable();

        // main.html 페이지에서만 loadAndRenderData를 호출하도록 조건 추가
        if (document.body.classList.contains('main-page')) {
            // 초기 데이터 로드를 먼저 시작 (기본값 또는 URL 파라미터 기준)
            if (initialDate && initialGrade && initialClassroom) {
                loadAndRenderData(initialDate, initialGrade, initialClassroom);
            }
        }

        // 내 클래스 목록 로드 (비동기적으로 진행)
        await loadMyClasses();

        // 내 클래스 목록에서 첫 번째 항목을 가져와 초기 학년/반으로 설정
        // 만약 loadMyClasses가 나중에 완료되고, 첫 번째 클래스가 있다면
        // 현재 표시된 데이터(기본값)를 덮어쓰도록 트리거
        const firstClassItem = Array.from(myClassesList.querySelectorAll('li[data-grade][data-classroom]'))
            .find(item => /^\d+$/.test(item.dataset.grade || '') && /^\d+$/.test(item.dataset.classroom || ''));
        if (firstClassItem && titleGradeInput && titleClassInput) {
            const newInitialGrade = firstClassItem.dataset.grade;
            const newInitialClassroom = firstClassItem.dataset.classroom;
            
            // 현재 input 값과 다를 경우에만 업데이트 및 데이터 로드 트리거
            if (titleGradeInput.value !== newInitialGrade || titleClassInput.value !== newInitialClassroom) {
                titleGradeInput.value = newInitialGrade;
                titleClassInput.value = newInitialClassroom;
                // 디바운스된 핸들러를 직접 호출하여 데이터 로드
                handleTitleInputChange(); 
            }
        }

        // 내 클래스 추가 버튼 기능
        const addClassBtn = document.querySelector('.add-class-btn');
        const classPopupOverlay = document.getElementById('class-popup-overlay');
        const addClassCancelBtn = document.getElementById('add-class-cancel-btn');
        const addClassSubmitBtn = document.getElementById('add-class-submit-btn');
        const newClassNameInput = document.getElementById('new-class-name-input');
        // const myClassesList = document.getElementById('my-classes-list'); // 이미 위에서 선언됨

        if (addClassBtn && classPopupOverlay) {
            addClassBtn.addEventListener('click', () => {
                classPopupOverlay.style.display = 'flex'; // 팝업 표시
            });

            // 팝업 닫기 (취소 버튼 클릭 시)
            if (addClassCancelBtn) {
                addClassCancelBtn.addEventListener('click', () => {
                    classPopupOverlay.style.display = 'none'; // 팝업 숨기기
                    newClassNameInput.value = ''; // 입력 필드 초기화
                });
            }

            // 팝업 닫기 (오버레이 외부 클릭 시)
            classPopupOverlay.addEventListener('click', (e) => {
                if (e.target === classPopupOverlay) {
                    classPopupOverlay.style.display = 'none';
                    newClassNameInput.value = ''; // 입력 필드 초기화
                }
            });

            // 클래스 추가 (확인 버튼 클릭 시)
            if (addClassSubmitBtn && newClassNameInput) {
                addClassSubmitBtn.addEventListener('click', async () => {
                    const invitationCode = newClassNameInput.value.trim().toUpperCase();
                    if (!invitationCode) {
                        alert('초대코드를 입력해주세요.');
                        return;
                    }

                    if (invitationCode.length !== 6) {
                        alert('초대 코드는 6자리여야 합니다.');
                        return;
                    }

                    const originalButtonText = addClassSubmitBtn.textContent;
                    addClassSubmitBtn.disabled = true;
                    addClassSubmitBtn.textContent = '추가 중...';

                    try {
                        const response = await fetch('/api/add_class_by_code', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({ invite_code: invitationCode }),
                        });
                        const result = await response.json();

                        if (result.success) {
                            loadMyClasses(); // 클래스 목록 새로고침
                            newClassNameInput.value = ''; // 입력 필드 초기화
                            classPopupOverlay.style.display = 'none'; // 팝업 숨기기
                        } else {
                            alert(`클래스 추가 실패: ${result.message}`);
                        }
                    } catch (error) {
                        console.error('Error adding class by code:', error);
                        alert('클래스 추가 중 오류가 발생했습니다.');
                    } finally {
                        addClassSubmitBtn.disabled = false;
                        addClassSubmitBtn.textContent = originalButtonText;
                    }
                });
            }
        }

    });
})();