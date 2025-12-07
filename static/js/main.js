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
                    listItem.classList.add('my-class-item'); // 새로운 클래스 추가

                    listItem.innerHTML = `
                        <span class="class-info">${cls.grade}학년 ${cls.classroom}반</span>
                    `;

                    // 클래스 정보 클릭 시 페이지 이동
                    listItem.querySelector('.class-info').addEventListener('click', () => {
                        window.location.href = `/class/${cls.grade}-${cls.classroom}`;
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

        // 급식 데이터 불러오기 및 렌더링
        if (shouldFetchMeal && mealContent) {
            // 급식 패널 제목 업데이트
            if (mealDateDisplay) {
                const month = parseInt(date.substring(4, 6), 10);
                const day = parseInt(date.substring(6, 8), 10);
                mealDateDisplay.textContent = `${month}월 ${day}일 급식`;
            }

            // Fetch data and wait for minimum delay simultaneously
            const mealData = await fetchMeal(date);
            // const [mealData] = await Promise.all([
            //     fetchMeal(date),
            //     minDelay(300) // FIX: Ensure loader is visible for at least 300ms
            // ]);

            mealContent.innerHTML = ''; // 새로운 데이터가 올 때만 지움
            renderMeal(mealData);
            if (mealLoading) {
                mealLoading.style.display = 'none';
            }
            lastFetchedDate = date; // 성공적으로 가져왔으면 업데이트
        }

        // 시간표 데이터 불러오기 및 렌더링
        if (shouldFetchTimetable && timetableContainer) {
            // Fetch data and wait for minimum delay simultaneously
            const timetableData = await fetchTimetable(date, grade, classroom);
            // const [timetableData] = await Promise.all([
            //     fetchTimetable(date, grade, classroom),
            //     minDelay(300) // FIX: Ensure loader is visible for at least 300ms
            // ]);

            timetableContainer.innerHTML = ''; // 새로운 데이터가 올 때만 지움
            renderTimetable(timetableData);
            if (timetableLoading) {
                timetableLoading.style.visibility = 'hidden'; // FIX: Use visibility
            }
            lastFetchedDate = date; // 성공적으로 가져왔으면 업데이트
            lastFetchedGrade = grade;
            lastFetchedClassroom = classroom;
        }

        // 만약 아무것도 가져오지 않았다면 로딩 인디케이터를 숨김 (초기 로드 시 등)
        if (mealLoading && !shouldFetchMeal) {
            mealLoading.style.display = 'none';
        }
        if (timetableLoading && !shouldFetchTimetable) {
            timetableLoading.style.visibility = 'hidden'; // FIX: Use visibility
        }
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
        const firstClassItem = myClassesList.querySelector('li[data-grade][data-classroom]');
        if (firstClassItem) {
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
                            // 선택적으로 성공 메시지를 표시할 수 있습니다.
                            // alert('클래스가 성공적으로 추가되었습니다!');
                        } else {
                            alert(`클래스 추가 실패: ${result.message}`);
                        }
                    } catch (error) {
                        console.error('Error adding class by code:', error);
                        alert('클래스 추가 중 오류가 발생했습니다.');
                    }
                });
            }
        }

    });
})();