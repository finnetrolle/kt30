/**
 * JavaScript for the results page
 */

/**
 * Toggle phase visibility
 */
function togglePhase(headerElement) {
    const content = headerElement.nextElementSibling;
    const isCollapsed = headerElement.classList.contains('collapsed');
    
    if (isCollapsed) {
        headerElement.classList.remove('collapsed');
        content.style.display = 'block';
    } else {
        headerElement.classList.add('collapsed');
        content.style.display = 'none';
    }
}

/**
 * Toggle work package visibility
 */
function toggleWorkPackage(headerElement) {
    const content = headerElement.nextElementSibling;
    const isCollapsed = headerElement.classList.contains('collapsed');
    
    if (isCollapsed) {
        headerElement.classList.remove('collapsed');
        content.style.display = 'block';
    } else {
        headerElement.classList.add('collapsed');
        content.style.display = 'none';
    }
}

/**
 * Export analysis result as JSON file
 */
function exportAsJSON() {
    if (typeof analysisResult === 'undefined') {
        alert('Данные результатов недоступны');
        return;
    }
    
    const dataStr = JSON.stringify(analysisResult, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = 'wbs_analysis_result.json';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

/**
 * Initialize page on load
 */
document.addEventListener('DOMContentLoaded', function() {
    // Expand all phases by default
    const phaseHeaders = document.querySelectorAll('.phase-header');
    phaseHeaders.forEach(header => {
        // Phases are expanded by default, no action needed
    });
    
    // Add keyboard navigation
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            // Collapse all on Escape
            phaseHeaders.forEach(header => {
                if (!header.classList.contains('collapsed')) {
                    togglePhase(header);
                }
            });
        }
    });
});
