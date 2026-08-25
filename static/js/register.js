document.addEventListener('DOMContentLoaded', () => {
    /* 비밀번호 표시 토글 */
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = btn.dataset.target;
            const inp = document.getElementById(id);
            if (!inp) return;
            inp.type = inp.type === 'password' ? 'text' : 'password';
            btn.textContent = inp.type === 'password' ? '보기' : '숨기기';
        });
    });

    /* 학번 숫자만 허용 */
    const sn = document.getElementById('student_no');
    if (sn) {
        sn.addEventListener('input', () => {
            sn.value = sn.value.replace(/\D/g, '').slice(0, 5);
        });
    }

    /* 비밀번호 복잡도 검사: 소문자, 대문자, 숫자, 특수문자 중 3가지 이상 */
    function pwClassCount(pw) {
        let count = 0;
        if (/[a-z]/.test(pw)) count++;
        if (/[A-Z]/.test(pw)) count++;
        if (/[0-9]/.test(pw)) count++;
        if (/[^A-Za-z0-9]/.test(pw)) count++;
        return count;
    }

    const pw = document.getElementById('pwd');
    const pw2 = document.getElementById('pwd2');
    const pwHint = document.getElementById('pwHint');
    const pwWarning = document.getElementById('pwWarning');
    const submitBtn = document.getElementById('submitBtn');
    const registerForm = document.getElementById('registerForm');

    function validatePwLive() {
        const val = pw.value || "";
        if (val.length > 0 && val.length < 8) {
            pwHint.style.display = 'none';
            pwWarning.style.display = 'block';
            pwWarning.textContent = '비밀번호는 8자 이상이어야 합니다.';
            submitBtn.disabled = true;
        } else if (val.length > 0 && pwClassCount(val) < 3) {
            pwHint.style.display = 'none';
            pwWarning.style.display = 'block';
            pwWarning.textContent = '비밀번호는 소문자, 대문자, 숫자, 특수문자 중 3종류 이상을 조합해야 합니다.';
            submitBtn.disabled = true;
        } else {
            pwHint.style.display = 'block';
            pwWarning.style.display = 'none';
            pwWarning.textContent = '';
            submitBtn.disabled = false;
        }
    }

    if (pw) {
        pw.addEventListener('input', validatePwLive);
    }

    /* 최종 제출 전 클라이언트 체크(서버 검증은 유지) */
    if (registerForm) {
        registerForm.addEventListener('submit', function(e) {
            const p = pw.value;
            const p2 = pw2.value;
            if (p !== p2) {
                e.preventDefault();
                alert('비밀번호가 일치하지 않습니다.');
                return;
            }
            if (p.length < 8) {
                e.preventDefault();
                alert('비밀번호는 8자 이상이어야 합니다.');
                return;
            }
            if (pwClassCount(p) < 3) {
                e.preventDefault();
                alert('비밀번호는 소문자·대문자·숫자·특수문자 중 3가지 이상을 포함해야 합니다.');
                return;
            }
        });
    }
});
