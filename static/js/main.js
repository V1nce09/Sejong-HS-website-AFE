(function() {
    /* --- DOM 요소 --- */
    const queryForm = document.getElementById('queryForm');
    const dateInput = document.getElementById('date');
    const gradeInput = document.getElementById('grade'); // 사이드바 학년
    const classroomInput = document.getElementById('classroom'); // 사이드바 반
    const timetableContainer = document.getElementById('timetable-data-container');
    const timetableLoading = document.getElementById('timetable-loading');

    // 제목 부분의 새로운 input 요소
    const titleGradeInput = document.getElementById('title-grade-input');
    const titleClassInput = document.getElementById('title-class-input');
    const titleDateInput = document.getElementById('title-date-input');

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
        // 학년에 따라 반의 최댓값 동적 변경
        const newMaxClass = (parseInt(grade, 10) === 2) ? 10 : 9;
        titleClassInput.setAttribute('max', newMaxClass);

        // 현재 반이 새로운 최댓값을 초과하면 조정
        if (parseInt(classroom, 10) > newMaxClass) {
            classroom = newMaxClass.toString();
        }

        // 컨텐츠 초기화
        timetableContainer.innerHTML = '';
        mealContent.innerHTML = '';
        
        // 로딩 인디케이터를 명시적으로 표시
        mealLoading.style.display = 'block';
        timetableLoading.style.display = 'block';

        const dateObj = new Date(date.substring(0, 4), date.substring(4, 6) - 1, date.substring(6, 8));
        mealDateDisplay.innerHTML = `${dateObj.getMonth() + 1}월 ${dateObj.getDate()}일 급식<br><br>`;
        
        // input 값을 현재 값으로 설정
        const formattedDate = `${date.substring(0, 4)}-${date.substring(4, 6)}-${date.substring(6, 8)}`;
        titleDateInput.value = formattedDate;
        titleGradeInput.value = grade;
        titleClassInput.value = classroom;

        // 1. 급식 데이터 불러오기 및 렌더링
        const mealData = await fetchMeal(date);
        renderMeal(mealData);
        mealLoading.style.display = 'none';

        // 2. 시간표 데이터 불러오기 및 렌더링
        const timetableData = await fetchTimetable(date, grade, classroom);
        renderTimetable(timetableData);
        timetableLoading.style.display = 'none';
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
    }

    const handleTitleInputChange = debounce(_handleTitleInputChange, 500); // 0.5초 디바운스

    function setupTitleInputs() {
        // 값 변경 시 시각적 동기화 및 데이터 로드
        titleDateInput.addEventListener('change', handleTitleInputChange);
        titleGradeInput.addEventListener('change', handleTitleInputChange);
        titleGradeInput.addEventListener('input', function() {
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
        });

        titleClassInput.addEventListener('input', function() {
            let value = parseInt(this.value, 10);
            const min = parseInt(this.min, 10);
            // const max = parseInt(this.max, 10); // max는 동적으로 변경되므로 사용하지 않음

            if (isNaN(value)) {
                this.value = min;
            } else if (value < min) {
                this.value = min;
            } else if (value > 3) { // 사용자 요청: 4 이상이면 3으로 고정
                this.value = 3;
            }
        });

        // 마우스 휠 이벤트 (데이터 로드는 하지 않고 시각적 변경만)
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
            input.value = value;
            // 휠 이벤트 후에도 데이터 로드
            handleTitleInputChange();
        };

        titleGradeInput.addEventListener('wheel', handleWheel);
        titleClassInput.addEventListener('wheel', handleWheel);
    }

    // 페이지 로드 시 초기 데이터 로드
    document.addEventListener('DOMContentLoaded', () => {
        const body = document.body;
        const initialDate = body.dataset.initialDate;
        const initialGrade = body.dataset.initialGrade;
        const initialClassroom = body.dataset.initialClassroom;
        
        if (initialDate && initialGrade && initialClassroom) {
            loadAndRenderData(initialDate, initialGrade, initialClassroom);
        }
        
        // 제목 input에 이벤트 리스너 설정
        setupTitleInputs();
    });
})();