"""
Flask backend application for Technical Specification Analyzer.
"""
import os
import uuid
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.utils import secure_filename
from config import Config, config as app_config
from document_parser import parse_document
from openai_client import analyze_specification


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
    
    # Store analysis results in memory (in production, use a database)
    analysis_results = {}
    
    @app.route('/')
    def index():
        """Render the upload page."""
        logger.info("Rendering upload page")
        return render_template('index.html')
    
    @app.route('/upload', methods=['POST'])
    def upload_file():
        """Handle file upload and analysis."""
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
            return jsonify({'error': 'Invalid file type. Please upload a .doc or .docx file'}), 400
        
        try:
            # Generate unique filename
            filename = secure_filename(file.filename)
            unique_id = str(uuid.uuid4())
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            saved_filename = f"{timestamp}_{unique_id}_{filename}"
            filepath = os.path.join(Config.UPLOAD_FOLDER, saved_filename)
            
            # Save the file
            logger.info(f"[{request_id}] Saving file to: {filepath}")
            file.save(filepath)
            file_size = os.path.getsize(filepath)
            logger.info(f"[{request_id}] File saved successfully. Size: {file_size} bytes")
            
            # Parse the document
            logger.info(f"[{request_id}] Starting document parsing...")
            document_content = parse_document(filepath)
            text_length = len(document_content['raw_text'])
            sections_count = len(document_content['structure'].get('sections', []))
            tables_count = len(document_content.get('tables', []))
            logger.info(f"[{request_id}] Document parsed successfully:")
            logger.info(f"[{request_id}]   - Text length: {text_length} characters")
            logger.info(f"[{request_id}]   - Sections found: {sections_count}")
            logger.info(f"[{request_id}]   - Tables found: {tables_count}")
            
            # Prepare text for analysis
            analysis_text = document_content['raw_text']
            
            # Add structure information if available
            if document_content['structure']['sections']:
                analysis_text += "\n\nСтруктура документа:\n"
                for section in document_content['structure']['sections']:
                    indent = "  " * (section['level'] - 1)
                    analysis_text += f"{indent}{section['title']}\n"
                    if section['content']:
                        analysis_text += f"{indent}  {section['content'][:200]}...\n"
            
            # Analyze with OpenAI
            logger.info(f"[{request_id}] Starting OpenAI analysis...")
            logger.info(f"[{request_id}]   - API Base: {Config.OPENAI_API_BASE}")
            logger.info(f"[{request_id}]   - Model: {Config.OPENAI_MODEL}")
            
            result = analyze_specification(analysis_text, request_id=request_id)
            
            if not result['success']:
                logger.error(f"[{request_id}] OpenAI analysis failed: {result['error']}")
                # Clean up uploaded file
                try:
                    os.remove(filepath)
                    logger.info(f"[{request_id}] Cleaned up uploaded file")
                except Exception as cleanup_error:
                    logger.warning(f"[{request_id}] Failed to cleanup file: {cleanup_error}")
                return jsonify({'error': result['error']}), 500
            
            logger.info(f"[{request_id}] OpenAI analysis completed successfully")
            if 'usage' in result:
                logger.info(f"[{request_id}] Token usage: {result['usage']}")
            
            # Clean up uploaded file
            try:
                os.remove(filepath)
                logger.info(f"[{request_id}] Cleaned up uploaded file")
            except Exception as cleanup_error:
                logger.warning(f"[{request_id}] Failed to cleanup file: {cleanup_error}")
            
            # Store result with unique ID
            result_id = unique_id
            analysis_results[result_id] = {
                'filename': filename,
                'timestamp': datetime.now().isoformat(),
                'result': result['data'],
                'usage': result.get('usage', {})
            }
            
            logger.info(f"[{request_id}] Analysis result stored with ID: {result_id}")
            
            # Return result ID for redirection
            return jsonify({
                'success': True,
                'result_id': result_id,
                'redirect_url': url_for('results', result_id=result_id)
            })
            
        except Exception as e:
            logger.exception(f"[{request_id}] Unexpected error during processing: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/results/<result_id>')
    def results(result_id):
        """Display the analysis results."""
        logger.info(f"Rendering results page for ID: {result_id}")
        result_data = analysis_results.get(result_id)
        
        if not result_data:
            logger.warning(f"Result not found for ID: {result_id}")
            return render_template('error.html', error='Result not found'), 404
        
        logger.info(f"Results found, rendering page for file: {result_data['filename']}")
        return render_template('results.html', 
                             result=result_data['result'],
                             filename=result_data['filename'],
                             timestamp=result_data['timestamp'],
                             usage=result_data.get('usage', {}))
    
    @app.route('/api/results/<result_id>')
    def api_results(result_id):
        """API endpoint to get results as JSON."""
        logger.info(f"API request for results ID: {result_id}")
        result_data = analysis_results.get(result_id)
        
        if not result_data:
            logger.warning(f"API: Result not found for ID: {result_id}")
            return jsonify({'error': 'Result not found'}), 404
        
        return jsonify(result_data)
    
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
