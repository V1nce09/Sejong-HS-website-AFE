(function() {
    /* --- DOM 요소 --- */
    const queryForm = document.getElementById('queryForm');
    const dateInput = document.getElementById('date');
    const gradeInput = document.getElementById('grade');
    const classroomInput = document.getElementById('classroom');
    const timetableContainer = document.getElementById('timetable-data-container');
    const timetableLoading = document.getElementById('timetable-loading');
    const timetableTitle = document.querySelector('#timetable-title-container h2');
    const mealContent = document.getElementById('meal-content');
    const mealLoading = document.getElementById('meal-loading');
    const mealDateDisplay = document.getElementById('meal-date-display');

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

    /* --- 데이터 렌더링 함수 --- */
    function renderTimetable(timetableData) {
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
        const url = `/api/data?date=${date}&data_type=meal`;
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            return data.meal || [];
        } catch (error) {
            console.error('Error fetching meal:', error);
            return [];
        }
    }

    async function fetchTimetable(date, grade, classroom) {
        const url = `/api/data?date=${date}&grade=${grade}&classroom=${classroom}&data_type=timetable`;
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            return data.timetable || [];
        } catch (error) {
            console.error('Error fetching timetable:', error);
            return [];
        }
    }

    /* --- 데이터 로드 및 렌더링 총괄 --- */
    async function loadAndRenderData(date, grade, classroom) {
        // 컨텐츠 초기화
        timetableContainer.innerHTML = '';
        mealContent.innerHTML = '';
        
        // 로딩 인디케이터를 명시적으로 표시
        mealLoading.style.display = 'block';
        timetableLoading.style.display = 'block';

        const dateObj = new Date(date.substring(0, 4), date.substring(4, 6) - 1, date.substring(6, 8));
        mealDateDisplay.innerHTML = `${dateObj.getMonth() + 1}월 ${dateObj.getDate()}일 급식<br><br>`;
        timetableTitle.textContent = `${grade}학년 ${classroom}반 시간표`;

        // 1. 급식 데이터 불러오기 및 렌더링
        const mealData = await fetchMeal(date);
        renderMeal(mealData);
        mealLoading.style.display = 'none';

        // 2. 시간표 데이터 불러오기 및 렌더링
        const timetableData = await fetchTimetable(date, grade, classroom);
        renderTimetable(timetableData);
        timetableLoading.style.display = 'none';
    }

    /* --- 이벤트 리스너 --- */
    queryForm.addEventListener("submit", function(e) {
        e.preventDefault();
        const date = dateInput.value.replaceAll("-", "");
        const grade = gradeInput.value;
        const classroom = classroomInput.value;
        loadAndRenderData(date, grade, classroom);
    });

    // 페이지 로드 시 초기 데이터 로드
    document.addEventListener('DOMContentLoaded', () => {
        const body = document.body;
        const initialDate = body.dataset.initialDate;
        const initialGrade = body.dataset.initialGrade;
        const initialClassroom = body.dataset.initialClassroom;
        
        if (initialDate && initialGrade && initialClassroom) {
            loadAndRenderData(initialDate, initialGrade, initialClassroom);
        }
    });
})();