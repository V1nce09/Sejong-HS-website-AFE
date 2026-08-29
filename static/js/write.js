const writeForm = document.getElementById('write-form');
    const imageInput = document.getElementById('post-images');
    const imageMessage = document.getElementById('post-image-message');
    const maxImages = 3;
    const sourceMaxBytes = 8 * 1024 * 1024;

    function validatePostImages() {
        const removeCount = document.querySelectorAll('input[name="remove_images"]:checked').length;
        const existingCount = document.querySelectorAll('.existing-image-item').length - removeCount;
        const files = Array.from(imageInput?.files || []);
        if (existingCount + files.length > maxImages) {
            imageMessage.textContent = '사진은 게시글당 최대 3장까지 첨부할 수 있습니다.';
            imageMessage.className = 'form-message error';
            return false;
        }
        if (files.some(file => file.size > sourceMaxBytes)) {
            imageMessage.textContent = '원본 이미지는 한 장당 8MB 이하만 첨부할 수 있습니다.';
            imageMessage.className = 'form-message error';
            return false;
        }
        imageMessage.textContent = files.length ? `${files.length}장 선택됨` : '';
        imageMessage.className = 'form-message';
        return true;
    }

    imageInput?.addEventListener('change', validatePostImages);
    document.querySelectorAll('input[name="remove_images"]').forEach(el => el.addEventListener('change', validatePostImages));
    writeForm.addEventListener('submit', function(event) {
        if (!validatePostImages()) {
            event.preventDefault();
            return;
        }
        const submitButton = document.getElementById('submit-post-btn');
        submitButton.disabled = true;
        submitButton.textContent = writeForm.dataset.editMode === '1' ? '수정 중...' : '작성 중...';
    });
