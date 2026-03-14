"""
Flask backend application for Technical Specification Analyzer.
"""
import os
import uuid
import json
import logging
import threading
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, session, Response
from werkzeug.utils import secure_filename
from config import Config, config as app_config
from document_parser import parse_document
from openai_client import analyze_specification
from excel_export import export_wbs_to_excel, calculate_project_duration_with_parallel, build_dependencies_matrix
from result_store import get_result_store
from progress_tracker import get_progress_store
from run_artifacts import RunArtifacts
from wbs_utils import canonicalize_wbs_result, has_legacy_root_phases, recover_wbs_from_artifacts


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def create_app(config_class=Config):
    """Create and configure the Flask application.
    
    Args:
        config_class: Configuration class to use
        
    Returns:
        Configured Flask application
    """
    logger.info("Creating Flask application...")
    
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize configuration
    config_class.init_app()
    logger.info("Configuration initialized")
    
    # File-based result storage with TTL cleanup
    store = get_result_store()
    progress_store = get_progress_store()

    def _normalize_result_payload(result_id: str, result_data: dict) -> dict:
        """Normalize stored result payloads and recover legacy malformed entries."""
        if not result_data:
            return result_data

        raw_result = result_data.get('result', {})
        normalized_result = canonicalize_wbs_result(raw_result)

        if has_legacy_root_phases(raw_result):
            recovered = recover_wbs_from_artifacts(result_data.get('artifacts_dir'))
            if recovered:
                logger.info("Recovered full WBS from artifacts for result ID: %s", result_id)
                normalized_result = recovered
            else:
                logger.warning("Legacy result detected for %s but artifacts recovery failed", result_id)

        if normalized_result != raw_result:
            updated = dict(result_data)
            updated['result'] = normalized_result
            store.save(result_id, updated)
            return updated

        return result_data
    
    # Optional authentication middleware
    auth_password = Config.APP_AUTH_PASSWORD
    if auth_password:
        logger.info("Authentication is ENABLED (APP_AUTH_PASSWORD is set)")
        
        @app.before_request
        def check_auth():
            """Check authentication for all routes except health and login."""
            # Skip auth for health check and static files
            if request.endpoint in ('health', 'login', 'static'):
                return None
            
            if not session.get('authenticated'):
                if request.endpoint == 'index':
                    return render_template('login.html')
                return jsonify({'error': 'Authentication required'}), 401
        
        @app.route('/login', methods=['POST'])
        def login():
            """Handle login."""
            password = request.form.get('password', '')
            if password == auth_password:
                session['authenticated'] = True
                logger.info("User authenticated successfully")
                return redirect(url_for('index'))
            else:
                logger.warning("Failed authentication attempt")
                return render_template('login.html', error='Неверный пароль'), 401
    else:
        logger.info("Authentication is DISABLED (APP_AUTH_PASSWORD not set)")
    
    @app.route('/')
    def index():
        """Render the upload page."""
        logger.info("Rendering upload page")
        return render_template('index.html')
    
    def _process_file_background(task_id: str, filepath: str, filename: str, unique_id: str, request_id: str):
        """Background processing function that runs in a separate thread.
        
        Args:
            task_id: Task ID for progress tracking
            filepath: Path to the uploaded file
            filename: Original filename
            unique_id: Unique ID for result storage
            request_id: Request ID for logging
        """
        tracker = progress_store.get(task_id)
        
        try:
            # Parse the document
            tracker.stage("📄 Парсинг документа...")
            logger.info(f"[{request_id}] Starting document parsing...")
            document_content = parse_document(filepath)
            text_length = len(document_content['raw_text'])
            sections_count = len(document_content['structure'].get('sections', []))
            tables_count = len(document_content.get('tables', []))
            logger.info(f"[{request_id}] Document parsed successfully:")
            logger.info(f"[{request_id}]   - Text length: {text_length} characters")
            logger.info(f"[{request_id}]   - Sections found: {sections_count}")
            logger.info(f"[{request_id}]   - Tables found: {tables_count}")

            if tracker:
                tracker.write_json_artifact("parsed_document.json", document_content)
            
            tracker.info(f"📄 Документ разобран: {text_length} символов, {sections_count} секций, {tables_count} таблиц")
            
            # Prepare text for analysis
            analysis_text = document_content['raw_text']
            
            # Add only a compact outline to avoid duplicating the full document content.
            if document_content['structure']['sections']:
                analysis_text += "\n\nОглавление документа:\n"
                for section in document_content['structure']['sections']:
                    indent = "  " * (section['level'] - 1)
                    analysis_text += f"{indent}{section['title']}\n"

            if tracker:
                tracker.write_text_artifact("analysis_input.txt", analysis_text)
                tracker.record_intermediate(
                    "document_prepared_for_analysis",
                    {
                        "text_length": len(analysis_text),
                        "sections_count": sections_count,
                        "tables_count": tables_count
                    }
                )
            
            # Analyze with OpenAI (multi-agent system)
            tracker.stage("🤖 Запуск мульти-агентного анализа...")
            logger.info(f"[{request_id}] Starting OpenAI analysis...")
            logger.info(f"[{request_id}]   - API Base: {Config.OPENAI_API_BASE}")
            logger.info(f"[{request_id}]   - Model: {Config.OPENAI_MODEL}")
            
            result = analyze_specification(analysis_text, request_id=request_id, progress_tracker=tracker)
            
            if not result['success']:
                logger.error(f"[{request_id}] OpenAI analysis failed: {result['error']}")
                if tracker:
                    tracker.write_json_artifact("analysis_error.json", result)
                # Clean up uploaded file
                try:
                    os.remove(filepath)
                    logger.info(f"[{request_id}] Cleaned up uploaded file")
                except Exception as cleanup_error:
                    logger.warning(f"[{request_id}] Failed to cleanup file: {cleanup_error}")
                tracker.error(f"Ошибка анализа: {result['error']}")
                return
            
            logger.info(f"[{request_id}] OpenAI analysis completed successfully")
            if 'usage' in result:
                logger.info(f"[{request_id}] Token usage: {result['usage']}")
            token_usage = result.get('metadata', {}).get('token_usage', {})
            normalized_result = canonicalize_wbs_result(result.get('data', {}))
            
            # Clean up uploaded file
            try:
                os.remove(filepath)
                logger.info(f"[{request_id}] Cleaned up uploaded file")
            except Exception as cleanup_error:
                logger.warning(f"[{request_id}] Failed to cleanup file: {cleanup_error}")
            
            # Store result with unique ID
            result_id = unique_id
            store.save(result_id, {
                'filename': filename,
                'timestamp': datetime.now().isoformat(),
                'result': normalized_result,
                'usage': result.get('usage', {}),
                'metadata': result.get('metadata', {}),
                'agent_conversation': result.get('agent_conversation', []),
                'token_usage': token_usage,
                'artifacts_dir': tracker.artifacts_dir if tracker else None
            })

            if tracker:
                tracker.write_json_artifact("final_result.json", {
                    'filename': filename,
                    'timestamp': datetime.now().isoformat(),
                    'result': normalized_result,
                    'usage': result.get('usage', {}),
                    'metadata': result.get('metadata', {}),
                    'agent_conversation': result.get('agent_conversation', []),
                    'token_usage': token_usage,
                    'result_id': result_id,
                    'artifacts_dir': tracker.artifacts_dir
                })
            
            logger.info(f"[{request_id}] Analysis result stored with ID: {result_id}")
            
            # Signal completion with redirect URL
            # We need app context for url_for, so build URL manually
            redirect_url = f"/results/{result_id}"
            tracker.complete(redirect_url, result_id, {
                'artifacts_dir': tracker.artifacts_dir if tracker else None
            })
            
        except Exception as e:
            logger.exception(f"[{request_id}] Unexpected error during background processing: {str(e)}")
            if tracker:
                tracker.write_json_artifact("background_error.json", {
                    "error": str(e),
                    "request_id": request_id
                })
            tracker.error(f"Непредвиденная ошибка: {str(e)}")
    
    @app.route('/upload', methods=['POST'])
    def upload_file():
        """Handle file upload — starts background processing and returns task_id."""
        request_id = str(uuid.uuid4())[:8]
        logger.info(f"[{request_id}] Starting file upload process")
        
        # Check if file was uploaded
        if 'file' not in request.files:
            logger.warning(f"[{request_id}] No file provided in request")
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        logger.info(f"[{request_id}] Received file: {file.filename}")
        
        # Check if file was selected
        if file.filename == '':
            logger.warning(f"[{request_id}] No file selected")
            return jsonify({'error': 'No file selected'}), 400
        
        # Check file extension
        if not Config.allowed_file(file.filename):
            logger.warning(f"[{request_id}] Invalid file type: {file.filename}")
            return jsonify({'error': 'Invalid file type. Please upload a .docx or .pdf file'}), 400
        
        try:
            # Generate unique filename
            filename = secure_filename(file.filename)
            unique_id = str(uuid.uuid4())
            task_id = str(uuid.uuid4())[:12]
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            saved_filename = f"{timestamp}_{unique_id}_{filename}"
            filepath = os.path.join(Config.UPLOAD_FOLDER, saved_filename)
            
            # Save the file
            logger.info(f"[{request_id}] Saving file to: {filepath}")
            file.save(filepath)
            file_size = os.path.getsize(filepath)
            logger.info(f"[{request_id}] File saved successfully. Size: {file_size} bytes")
            
            artifacts = RunArtifacts.create_for_upload(
                Config.ARTIFACTS_ROOT,
                unique_id,
                filename,
                filepath,
                metadata={
                    "task_id": task_id,
                    "request_id": request_id,
                    "saved_upload_path": filepath,
                    "saved_filename": saved_filename,
                    "file_size": file_size
                }
            )

            # Create progress tracker
            tracker = progress_store.create(task_id, run_artifacts=artifacts)
            tracker.info(f"📁 Файл «{filename}» загружен ({file_size} байт)")
            tracker.record_intermediate(
                "upload_saved",
                {
                    "filename": filename,
                    "saved_filename": saved_filename,
                    "file_size": file_size,
                    "request_id": request_id,
                    "task_id": task_id,
                    "artifacts_dir": tracker.artifacts_dir
                }
            )
            
            # Start background processing
            thread = threading.Thread(
                target=_process_file_background,
                args=(task_id, filepath, filename, unique_id, request_id),
                daemon=True
            )
            thread.start()
            
            logger.info(f"[{request_id}] Background processing started, task_id: {task_id}")
            
            # Return task_id for SSE subscription
            return jsonify({
                'success': True,
                'task_id': task_id
            })
            
        except Exception as e:
            logger.exception(f"[{request_id}] Unexpected error during upload: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/progress/<task_id>')
    def progress_stream(task_id):
        """SSE endpoint for streaming progress events.
        
        Args:
            task_id: Task ID to stream progress for
        """
        tracker = progress_store.get(task_id)
        if not tracker:
            return jsonify({'error': 'Task not found'}), 404
        
        def generate():
            """Generate SSE events from the progress tracker."""
            while True:
                event = tracker.get_event(timeout=30.0)
                
                if event is None:
                    # Send keepalive comment to prevent timeout
                    yield ": keepalive\n\n"
                    continue
                
                event_data = json.dumps(event, ensure_ascii=False)
                yield f"event: {event['type']}\ndata: {event_data}\n\n"
                
                # If this is a terminal event, stop streaming
                if event['type'] in ('complete', 'error'):
                    break
            
            # Clean up tracker after a delay
            # (give client time to process the final event)
            import time
            time.sleep(5)
            progress_store.remove(task_id)
        
        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive'
            }
        )
    
    @app.route('/results/<result_id>')
    def results(result_id):
        """Display the analysis results."""
        logger.info(f"Rendering results page for ID: {result_id}")
        result_data = _normalize_result_payload(result_id, store.get(result_id))
        
        if not result_data:
            logger.warning(f"Result not found for ID: {result_id}")
            return render_template('error.html', error='Result not found'), 404
        
        # Calculate actual duration considering parallel execution
        result = result_data['result']
        wbs_data = result.get('wbs', {}) if result else {}
        
        duration_info = calculate_project_duration_with_parallel(wbs_data)
        dependencies_matrix = build_dependencies_matrix(wbs_data)
        
        # Add calculated duration to project_info if available
        if 'project_info' in result:
            result['project_info']['calculated_duration_days'] = duration_info['total_days']
            result['project_info']['calculated_duration_weeks'] = duration_info['total_weeks']
        
        # Add dependencies matrix to result
        result['dependencies_matrix'] = dependencies_matrix
        
        logger.info(f"Results found, rendering page for file: {result_data['filename']}")
        logger.info(f"Calculated duration: {duration_info['total_days']} days ({duration_info['total_weeks']} weeks)")
        
        return render_template('results.html',
                             result=result,
                             result_id=result_id,
                             filename=result_data['filename'],
                             timestamp=result_data['timestamp'],
                             usage=result_data.get('usage', {}),
                             metadata=result_data.get('metadata', {}),
                             token_usage=result_data.get('token_usage', {}),
                             calculated_duration=duration_info)
    
    @app.route('/api/results/<result_id>')
    def api_results(result_id):
        """API endpoint to get results as JSON."""
        logger.info(f"API request for results ID: {result_id}")
        result_data = _normalize_result_payload(result_id, store.get(result_id))
        
        if not result_data:
            logger.warning(f"API: Result not found for ID: {result_id}")
            return jsonify({'error': 'Result not found'}), 404
        
        return jsonify(result_data)
    
    @app.route('/export/excel/<result_id>')
    def export_excel(result_id):
        """Export WBS results as Excel file."""
        logger.info(f"Excel export request for results ID: {result_id}")
        result_data = _normalize_result_payload(result_id, store.get(result_id))
        
        if not result_data:
            logger.warning(f"Excel export: Result not found for ID: {result_id}")
            return jsonify({'error': 'Result not found'}), 404
        
        try:
            excel_file, filename = export_wbs_to_excel(result_data['result'])
            logger.info(f"Excel export successful for ID: {result_id}")
            
            return send_file(
                excel_file,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename
            )
        except Exception as e:
            logger.exception(f"Excel export failed for ID: {result_id}: {str(e)}")
            return jsonify({'error': f'Failed to generate Excel: {str(e)}'}), 500
    
    @app.route('/health')
    def health():
        """Health check endpoint."""
        return jsonify({'status': 'healthy'})
    
    @app.errorhandler(413)
    def too_large(e):
        """Handle file too large error."""
        logger.warning(f"File too large error: {e}")
        return jsonify({'error': 'File is too large. Maximum size is 16MB'}), 413
    
    @app.errorhandler(500)
    def server_error(e):
        """Handle server error."""
        logger.error(f"Server error: {e}")
        return jsonify({'error': 'Internal server error'}), 500
    
    logger.info("Flask application created successfully")
    return app


# Create application instance
app = create_app()


if __name__ == '__main__':
    logger.info("Starting development server on http://0.0.0.0:8000")
    app.run(debug=True, host='0.0.0.0', port=8000)
