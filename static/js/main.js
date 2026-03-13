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
    const progressPanel = document.getElementById('progressPanel');
    const progressLog = document.getElementById('progressLog');
    const progressStage = document.getElementById('progressStage');
    const progressElapsed = document.getElementById('progressElapsed');
    
    let selectedFile = null;
    let elapsedTimer = null;
    let elapsedSeconds = 0;

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
        const allowedExtensions = ['docx', 'pdf'];
        const fileExtension = file.name.split('.').pop().toLowerCase();
        
        if (!allowedExtensions.includes(fileExtension)) {
            showError('Неверный формат файла. Пожалуйста, загрузите файл .docx или .pdf');
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
     * Upload file to server and subscribe to progress SSE
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
                // Upload accepted — subscribe to progress stream
                showProgressPanel();
                subscribeToProgress(result.task_id);
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
     * Show the progress panel and start elapsed timer
     */
    function showProgressPanel() {
        progressPanel.style.display = 'block';
        progressLog.innerHTML = '';
        elapsedSeconds = 0;
        progressElapsed.textContent = '0 сек';
        
        elapsedTimer = setInterval(function() {
            elapsedSeconds++;
            if (elapsedSeconds < 60) {
                progressElapsed.textContent = elapsedSeconds + ' сек';
            } else {
                const mins = Math.floor(elapsedSeconds / 60);
                const secs = elapsedSeconds % 60;
                progressElapsed.textContent = mins + ' мин ' + secs + ' сек';
            }
        }, 1000);
    }

    /**
     * Stop the elapsed timer
     */
    function stopElapsedTimer() {
        if (elapsedTimer) {
            clearInterval(elapsedTimer);
            elapsedTimer = null;
        }
    }

    /**
     * Subscribe to SSE progress stream
     */
    function subscribeToProgress(taskId) {
        const eventSource = new EventSource('/progress/' + taskId);
        
        // Handle stage events (major steps)
        eventSource.addEventListener('stage', function(e) {
            const data = JSON.parse(e.data);
            progressStage.textContent = data.message;
            addLogEntry(data.message, 'stage');
        });
        
        // Handle agent events
        eventSource.addEventListener('agent', function(e) {
            const data = JSON.parse(e.data);
            addLogEntry(data.message, 'agent');
        });
        
        // Handle info events
        eventSource.addEventListener('info', function(e) {
            const data = JSON.parse(e.data);
            addLogEntry(data.message, 'info');
        });
        
        // Handle completion
        eventSource.addEventListener('complete', function(e) {
            const data = JSON.parse(e.data);
            stopElapsedTimer();
            addLogEntry('✅ ' + data.message, 'complete');
            progressStage.textContent = '✅ Анализ завершён! Перенаправление...';
            
            // Remove spinner from header
            const spinnerEl = progressPanel.querySelector('.spinner-small');
            if (spinnerEl) {
                spinnerEl.style.display = 'none';
            }
            
            eventSource.close();
            
            // Redirect after a short delay
            setTimeout(function() {
                window.location.href = data.data.redirect_url;
            }, 1500);
        });
        
        // Handle error events from the server
        eventSource.addEventListener('error_event', function(e) {
            const data = JSON.parse(e.data);
            stopElapsedTimer();
            addLogEntry('❌ ' + data.message, 'error');
            progressStage.textContent = '❌ Ошибка';
            
            // Remove spinner from header
            const spinnerEl = progressPanel.querySelector('.spinner-small');
            if (spinnerEl) {
                spinnerEl.style.display = 'none';
            }
            
            showError(data.message);
            eventSource.close();
            setLoadingState(false);
        });
        
        // Handle SSE connection errors
        eventSource.onerror = function(e) {
            // EventSource will auto-reconnect, but if the server closed the stream
            // (after complete/error event), this is expected
            if (eventSource.readyState === EventSource.CLOSED) {
                return;
            }
            console.error('SSE connection error', e);
        };
        
        // Also listen for 'error' event type from our backend
        eventSource.addEventListener('error', function(e) {
            const data = JSON.parse(e.data);
            stopElapsedTimer();
            addLogEntry('❌ ' + data.message, 'error');
            progressStage.textContent = '❌ Ошибка';
            
            const spinnerEl = progressPanel.querySelector('.spinner-small');
            if (spinnerEl) {
                spinnerEl.style.display = 'none';
            }
            
            showError(data.message);
            eventSource.close();
            setLoadingState(false);
        });
    }

    /**
     * Add a log entry to the progress panel
     */
    function addLogEntry(message, type) {
        const entry = document.createElement('div');
        entry.className = 'progress-log-entry progress-log-' + type;
        
        const time = document.createElement('span');
        time.className = 'progress-log-time';
        const now = new Date();
        time.textContent = now.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        
        const text = document.createElement('span');
        text.className = 'progress-log-text';
        text.textContent = message;
        
        entry.appendChild(time);
        entry.appendChild(text);
        progressLog.appendChild(entry);
        
        // Auto-scroll to bottom
        progressLog.scrollTop = progressLog.scrollHeight;
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
