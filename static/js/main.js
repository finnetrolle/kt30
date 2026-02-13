/**
 * Main JavaScript for the upload page
 */

document.addEventListener('DOMContentLoaded', function() {
    const uploadForm = document.getElementById('uploadForm');
    const fileInput = document.getElementById('fileInput');
    const dropZone = document.getElementById('dropZone');
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const removeFile = document.getElementById('removeFile');
    const submitBtn = document.getElementById('submitBtn');
    const errorMessage = document.getElementById('errorMessage');
    
    let selectedFile = null;

    // Drag and drop handlers
    dropZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', function(e) {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', function(e) {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileSelection(files[0]);
        }
    });

    // File input change handler
    fileInput.addEventListener('change', function(e) {
        if (e.target.files.length > 0) {
            handleFileSelection(e.target.files[0]);
        }
    });

    // Remove file handler
    removeFile.addEventListener('click', function(e) {
        e.preventDefault();
        clearFileSelection();
    });

    // Form submit handler
    uploadForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        if (!selectedFile) {
            showError('Пожалуйста, выберите файл');
            return;
        }
        
        uploadFile(selectedFile);
    });

    /**
     * Handle file selection
     */
    function handleFileSelection(file) {
        // Validate file extension
        const allowedExtensions = ['doc', 'docx', 'pdf'];
        const fileExtension = file.name.split('.').pop().toLowerCase();
        
        if (!allowedExtensions.includes(fileExtension)) {
            showError('Неверный формат файла. Пожалуйста, загрузите файл .doc, .docx или .pdf');
            clearFileSelection();
            return;
        }
        
        // Validate file size (16MB max)
        const maxSize = 16 * 1024 * 1024;
        if (file.size > maxSize) {
            showError('Файл слишком большой. Максимальный размер: 16MB');
            clearFileSelection();
            return;
        }
        
        selectedFile = file;
        fileName.textContent = file.name;
        fileInfo.style.display = 'flex';
        dropZone.style.display = 'none';
        submitBtn.disabled = false;
        hideError();
    }

    /**
     * Clear file selection
     */
    function clearFileSelection() {
        selectedFile = null;
        fileInput.value = '';
        fileName.textContent = '';
        fileInfo.style.display = 'none';
        dropZone.style.display = 'block';
        submitBtn.disabled = true;
        hideError();
    }

    /**
     * Upload file to server
     */
    async function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        
        // Show loading state
        setLoadingState(true);
        hideError();
        
        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                // Redirect to results page
                window.location.href = result.redirect_url;
            } else {
                showError(result.error || 'Произошла ошибка при обработке файла');
                setLoadingState(false);
            }
        } catch (error) {
            showError('Ошибка сети: ' + error.message);
            setLoadingState(false);
        }
    }

    /**
     * Set loading state
     */
    function setLoadingState(loading) {
        const btnText = submitBtn.querySelector('.btn-text');
        const btnLoader = submitBtn.querySelector('.btn-loader');
        
        if (loading) {
            btnText.style.display = 'none';
            btnLoader.style.display = 'flex';
            submitBtn.disabled = true;
        } else {
            btnText.style.display = 'inline';
            btnLoader.style.display = 'none';
            submitBtn.disabled = !selectedFile;
        }
    }

    /**
     * Show error message
     */
    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.style.display = 'block';
    }

    /**
     * Hide error message
     */
    function hideError() {
        errorMessage.style.display = 'none';
    }
});
