
from flask import Flask, render_template_string, request, send_file, jsonify
from rembg import remove
from PIL import Image
import io
import os
import uuid

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Ensure temp folder exists
UPLOAD_FOLDER = 'temp'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#00C853">
    <meta name="description" content="Free AI Background Remover - Remove background from images instantly">
    <title>BG Remover Pro - Free AI Background Removal</title>
    <style>
        /* ===== RESET & BASE ===== */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary: #00C853;
            --primary-dark: #00A344;
            --primary-light: #69F0AE;
            --dark: #0a0a0a;
            --card: #1a1a1a;
            --card-hover: #222222;
            --text: #ffffff;
            --text-dim: #aaaaaa;
            --text-muted: #666666;
            --border: #333333;
            --error: #ff5252;
            --error-bg: rgba(255, 82, 82, 0.1);
            --success: #00C853;
            --success-bg: rgba(0, 200, 83, 0.1);
            --warning: #ffd740;
        }

        html {
            font-size: 16px;
            -webkit-text-size-adjust: 100%;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: var(--dark);
            color: var(--text);
            min-height: 100vh;
            line-height: 1.6;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }

        /* ===== CONTAINER ===== */
        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 16px;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        /* ===== HEADER ===== */
        .header {
            text-align: center;
            padding: 32px 20px;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            border-radius: 20px;
            margin-bottom: 24px;
            position: relative;
            overflow: hidden;
        }

        .header::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="0.5"/></svg>');
            background-size: 60px;
            opacity: 0.3;
        }

        .header-content {
            position: relative;
            z-index: 1;
        }

        .header h1 {
            font-size: clamp(1.6rem, 5vw, 2.4rem);
            font-weight: 900;
            margin-bottom: 8px;
            letter-spacing: -0.5px;
        }

        .header p {
            font-size: clamp(0.85rem, 2.5vw, 1rem);
            opacity: 0.95;
            font-weight: 400;
            margin-bottom: 12px;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(255,255,255,0.2);
            backdrop-filter: blur(10px);
            padding: 6px 14px;
            border-radius: 50px;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .badge-dot {
            width: 8px;
            height: 8px;
            background: var(--primary-light);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        /* ===== UPLOAD CARD ===== */
        .upload-card {
            background: var(--card);
            border-radius: 20px;
            padding: 24px;
            border: 1px solid var(--border);
            margin-bottom: 20px;
            transition: transform 0.3s;
        }

        .upload-card:hover {
            transform: translateY(-2px);
        }

        .section-title {
            font-size: 1.1rem;
            font-weight: 700;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text);
        }

        .upload-area {
            border: 3px dashed var(--border);
            border-radius: 16px;
            padding: 48px 24px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            position: relative;
            background: var(--dark);
        }

        .upload-area:hover {
            border-color: var(--primary);
            background: rgba(0, 200, 83, 0.05);
        }

        .upload-area.dragover {
            border-color: var(--primary);
            background: rgba(0, 200, 83, 0.1);
            transform: scale(1.02);
        }

        .upload-icon {
            font-size: 56px;
            margin-bottom: 16px;
            display: block;
        }

        .upload-title {
            font-size: 1.2rem;
            font-weight: 700;
            margin-bottom: 8px;
            color: var(--text);
        }

        .upload-subtitle {
            color: var(--text-dim);
            font-size: 0.9rem;
            margin-bottom: 16px;
        }

        .file-types {
            display: flex;
            gap: 8px;
            justify-content: center;
            flex-wrap: wrap;
        }

        .badge-type {
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: var(--dark);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
        }

        #fileInput { display: none; }

        /* ===== PREVIEW SECTION ===== */
        .preview-section {
            display: none;
            animation: fadeInUp 0.5s ease;
        }

        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .preview-card {
            background: var(--card);
            border-radius: 20px;
            padding: 20px;
            border: 1px solid var(--border);
            margin-bottom: 20px;
        }

        .image-comparison {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 20px;
        }

        .image-box {
            background: var(--dark);
            border-radius: 12px;
            overflow: hidden;
            border: 2px solid var(--border);
            position: relative;
            min-height: 200px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .image-box img {
            width: 100%;
            height: auto;
            max-height: 400px;
            object-fit: contain;
            display: block;
        }

        .image-label {
            position: absolute;
            top: 10px;
            left: 10px;
            background: var(--primary);
            color: var(--dark);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.7rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            z-index: 10;
        }

        .image-label.result {
            background: var(--success);
        }

        /* ===== PROCESSING ===== */
        .processing {
            display: none;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 40px;
            min-height: 200px;
        }

        .spinner {
            width: 50px;
            height: 50px;
            border: 4px solid var(--border);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-bottom: 16px;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .processing-text {
            color: var(--text-dim);
            font-size: 0.95rem;
            font-weight: 500;
        }

        .processing-sub {
            color: var(--text-muted);
            font-size: 0.8rem;
            margin-top: 4px;
        }

        /* ===== ACTION BUTTONS ===== */
        .action-btns {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }

        .btn {
            flex: 1;
            min-width: 120px;
            padding: 14px 20px;
            border-radius: 12px;
            font-size: 0.95rem;
            font-weight: 700;
            cursor: pointer;
            border: none;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            position: relative;
            overflow: hidden;
        }

        .btn::after {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 0;
            height: 0;
            background: rgba(255,255,255,0.2);
            border-radius: 50%;
            transform: translate(-50%, -50%);
            transition: width 0.6s, height 0.6s;
        }

        .btn:active::after {
            width: 300px;
            height: 300px;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: var(--dark);
            box-shadow: 0 4px 15px rgba(0, 200, 83, 0.3);
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 200, 83, 0.4);
        }

        .btn-success {
            background: linear-gradient(135deg, #69F0AE, var(--primary));
            color: var(--dark);
            box-shadow: 0 4px 15px rgba(105, 240, 174, 0.3);
        }

        .btn-success:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(105, 240, 174, 0.4);
        }

        .btn-secondary {
            background: var(--card);
            color: var(--text);
            border: 2px solid var(--border);
        }

        .btn-secondary:hover {
            border-color: var(--primary);
            transform: translateY(-2px);
        }

        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none !important;
        }

        .btn-icon {
            font-size: 1.2em;
        }

        /* ===== STATUS ===== */
        .status {
            margin-top: 16px;
            padding: 14px 20px;
            border-radius: 12px;
            text-align: center;
            font-weight: 600;
            font-size: 0.9rem;
            display: none;
            animation: slideIn 0.3s ease;
        }

        @keyframes slideIn {
            from { transform: translateY(-10px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }

        .status.success {
            background: var(--success-bg);
            color: var(--success);
            border: 1px solid var(--primary);
        }

        .status.error {
            background: var(--error-bg);
            color: var(--error);
            border: 1px solid var(--error);
        }

        /* ===== FEATURES ===== */
        .features {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
            margin: 32px 0;
        }

        .feature {
            background: var(--card);
            border-radius: 16px;
            padding: 24px 16px;
            text-align: center;
            border: 1px solid var(--border);
            transition: all 0.3s ease;
        }

        .feature:hover {
            transform: translateY(-4px);
            border-color: var(--primary);
            background: var(--card-hover);
        }

        .feature-icon {
            font-size: 36px;
            margin-bottom: 12px;
            display: block;
        }

        .feature h4 {
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 6px;
            color: var(--text);
        }

        .feature p {
            font-size: 0.8rem;
            color: var(--text-dim);
            line-height: 1.4;
        }

        /* ===== FOOTER ===== */
        .footer {
            text-align: center;
            padding: 32px 20px;
            color: var(--text-muted);
            font-size: 0.85rem;
            border-top: 1px solid var(--border);
            margin-top: auto;
        }

        .footer a {
            color: var(--primary);
            text-decoration: none;
        }

        /* ===== RESPONSIVE ===== */
        @media (max-width: 768px) {
            .container {
                padding: 12px;
            }

            .header {
                padding: 24px 16px;
                border-radius: 16px;
            }

            .upload-card {
                padding: 20px;
            }

            .upload-area {
                padding: 36px 20px;
            }

            .upload-icon {
                font-size: 44px;
            }

            .image-comparison {
                grid-template-columns: 1fr;
                gap: 12px;
            }

            .image-box {
                min-height: 150px;
            }

            .image-box img {
                max-height: 300px;
            }

            .action-btns {
                flex-direction: column;
            }

            .btn {
                width: 100%;
                min-width: unset;
            }

            .features {
                grid-template-columns: 1fr;
                gap: 12px;
            }

            .feature {
                display: flex;
                align-items: center;
                text-align: left;
                gap: 16px;
                padding: 20px;
            }

            .feature-icon {
                margin-bottom: 0;
                font-size: 32px;
            }
        }

        @media (max-width: 480px) {
            .header h1 {
                font-size: 1.4rem;
            }

            .upload-title {
                font-size: 1.05rem;
            }

            .upload-subtitle {
                font-size: 0.85rem;
            }

            .btn {
                padding: 12px 16px;
                font-size: 0.9rem;
            }

            .image-label {
                font-size: 0.65rem;
                padding: 3px 8px;
            }
        }

        /* ===== DARK MODE SUPPORT ===== */
        @media (prefers-color-scheme: dark) {
            body {
                background: var(--dark);
            }
        }

        /* ===== REDUCED MOTION ===== */
        @media (prefers-reduced-motion: reduce) {
            * {
                animation-duration: 0.01ms !important;
                transition-duration: 0.01ms !important;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <div class="header-content">
                <h1>🎨 BG Remover Pro</h1>
                <p>Free AI Background Removal — No Signup, No Watermark</p>
                <span class="badge">
                    <span class="badge-dot"></span>
                    100% FREE • UNLIMITED • PRIVATE
                </span>
            </div>
        </header>

        <!-- Upload Section -->
        <div class="upload-card" id="uploadCard">
            <div class="section-title">
                <span>📤</span>
                <span>Upload Your Image</span>
            </div>

            <div class="upload-area" id="uploadArea">
                <input type="file" id="fileInput" accept="image/png,image/jpeg,image/jpg,image/webp" hidden>
                <span class="upload-icon">📁</span>
                <div class="upload-title">Drop your image here</div>
                <div class="upload-subtitle">or click to browse from device</div>
                <div class="file-types">
                    <span class="badge-type">PNG</span>
                    <span class="badge-type">JPG</span>
                    <span class="badge-type">WEBP</span>
                </div>
            </div>
        </div>

        <!-- Preview Section -->
        <div class="preview-section" id="previewSection">
            <div class="preview-card">
                <div class="image-comparison">
                    <div class="image-box">
                        <span class="image-label">Original</span>
                        <img id="originalImg" alt="Original image" style="display: none;">
                    </div>
                    <div class="image-box">
                        <span class="image-label result">No Background</span>
                        <img id="resultImg" alt="Result image" style="display: none;">
                        <div class="processing" id="processing">
                            <div class="spinner"></div>
                            <div class="processing-text">Removing background...</div>
                            <div class="processing-sub">AI is processing your image</div>
                        </div>
                    </div>
                </div>

                <div class="action-btns">
                    <button class="btn btn-primary" id="removeBtn">
                        <span class="btn-icon">✨</span>
                        <span>Remove BG</span>
                    </button>
                    <button class="btn btn-success" id="downloadBtn" style="display: none;">
                        <span class="btn-icon">💾</span>
                        <span>Download PNG</span>
                    </button>
                    <button class="btn btn-secondary" id="newBtn">
                        <span class="btn-icon">🔄</span>
                        <span>New Image</span>
                    </button>
                </div>

                <div class="status" id="status"></div>
            </div>
        </div>

        <!-- Features -->
        <div class="features">
            <div class="feature">
                <span class="feature-icon">🚀</span>
                <div>
                    <h4>Lightning Fast</h4>
                    <p>AI powered instant removal in seconds</p>
                </div>
            </div>
            <div class="feature">
                <span class="feature-icon">🔒</span>
                <div>
                    <h4>100% Private</h4>
                    <p>Images are never stored on our servers</p>
                </div>
            </div>
            <div class="feature">
                <span class="feature-icon">💯</span>
                <div>
                    <h4>Free Forever</h4>
                    <p>No limits, no fees, no watermarks</p>
                </div>
            </div>
        </div>

        <!-- Footer -->
        <footer class="footer">
            <p>Made with 💚 for Creators | Open Source AI | Free Forever</p>
        </footer>
    </div>

    <script>
        // ===== DOM Elements =====
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const uploadCard = document.getElementById('uploadCard');
        const previewSection = document.getElementById('previewSection');
        const originalImg = document.getElementById('originalImg');
        const resultImg = document.getElementById('resultImg');
        const processing = document.getElementById('processing');
        const removeBtn = document.getElementById('removeBtn');
        const downloadBtn = document.getElementById('downloadBtn');
        const newBtn = document.getElementById('newBtn');
        const status = document.getElementById('status');

        let currentFile = null;
        let resultBlob = null;

        // ===== Event Listeners =====
        uploadArea.addEventListener('click', () => fileInput.click());

        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadArea.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFile(files[0]);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFile(e.target.files[0]);
            }
        });

        // ===== Handle File =====
        function handleFile(file) {
            // Validate file type
            const validTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'];
            if (!validTypes.includes(file.type)) {
                showStatus('❌ Please upload PNG, JPG, or WEBP image!', 'error');
                return;
            }

            // Validate file size (16MB)
            if (file.size > 16 * 1024 * 1024) {
                showStatus('❌ File size must be under 16MB!', 'error');
                return;
            }

            currentFile = file;

            // Show preview
            const reader = new FileReader();
            reader.onload = (e) => {
                originalImg.src = e.target.result;
                originalImg.style.display = 'block';
                showPreviewSection();
                hideStatus();
            };
            reader.onerror = () => {
                showStatus('❌ Error reading file. Please try again.', 'error');
            };
            reader.readAsDataURL(file);
        }

        // ===== Show Preview Section =====
        function showPreviewSection() {
            uploadCard.style.display = 'none';
            previewSection.style.display = 'block';
            resultImg.style.display = 'none';
            processing.style.display = 'none';
            removeBtn.style.display = 'inline-flex';
            removeBtn.disabled = false;
            downloadBtn.style.display = 'none';

            // Scroll to preview
            setTimeout(() => {
                previewSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 100);
        }

        // ===== Remove Background =====
        removeBtn.addEventListener('click', async () => {
            if (!currentFile) {
                showStatus('❌ No image selected!', 'error');
                return;
            }

            // UI state: processing
            removeBtn.disabled = true;
            processing.style.display = 'flex';
            resultImg.style.display = 'none';
            hideStatus();

            const formData = new FormData();
            formData.append('image', currentFile);

            try {
                // 60 second timeout
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 60000);

                const response = await fetch('/remove-bg', {
                    method: 'POST',
                    body: formData,
                    signal: controller.signal
                });

                clearTimeout(timeoutId);

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || 'Processing failed. Please try again.');
                }

                resultBlob = await response.blob();
                const url = URL.createObjectURL(resultBlob);

                resultImg.src = url;
                resultImg.onload = () => {
                    processing.style.display = 'none';
                    resultImg.style.display = 'block';
                    removeBtn.style.display = 'none';
                    downloadBtn.style.display = 'inline-flex';
                    showStatus('✅ Background removed successfully!', 'success');
                };

                resultImg.onerror = () => {
                    processing.style.display = 'none';
                    removeBtn.disabled = false;
                    showStatus('❌ Error displaying result. Please try again.', 'error');
                };

            } catch (error) {
                processing.style.display = 'none';
                removeBtn.disabled = false;

                if (error.name === 'AbortError') {
                    showStatus('⏱️ Request timed out. Try a smaller image.', 'error');
                } else {
                    showStatus('❌ ' + error.message, 'error');
                }
            }
        });

        // ===== Download =====
        downloadBtn.addEventListener('click', () => {
            if (!resultBlob) {
                showStatus('❌ No result to download!', 'error');
                return;
            }

            const url = URL.createObjectURL(resultBlob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'no-bg-' + Date.now() + '.png';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            showStatus('💾 Download started!', 'success');
        });

        // ===== New Image =====
        newBtn.addEventListener('click', () => {
            currentFile = null;
            resultBlob = null;
            fileInput.value = '';
            originalImg.src = '';
            originalImg.style.display = 'none';
            resultImg.src = '';
            resultImg.style.display = 'none';

            uploadCard.style.display = 'block';
            previewSection.style.display = 'none';
            hideStatus();

            // Scroll to top
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });

        // ===== Status Messages =====
        function showStatus(message, type) {
            status.textContent = message;
            status.className = 'status ' + type;
            status.style.display = 'block';

            // Auto hide after 5 seconds
            setTimeout(() => {
                status.style.opacity = '0';
                setTimeout(() => {
                    status.style.display = 'none';
                    status.style.opacity = '1';
                }, 300);
            }, 5000);
        }

        function hideStatus() {
            status.style.display = 'none';
            status.style.opacity = '1';
        }

        // ===== Touch Support for Mobile =====
        let touchStartY = 0;
        document.addEventListener('touchstart', (e) => {
            touchStartY = e.touches[0].clientY;
        }, { passive: true });

        document.addEventListener('touchmove', (e) => {
            const touchY = e.touches[0].clientY;
            const diff = touchStartY - touchY;

            // Prevent pull-to-refresh when at top
            if (window.scrollY === 0 && diff < 0) {
                e.preventDefault();
            }
        }, { passive: false });

        // Prevent double tap zoom
        let lastTouchEnd = 0;
        document.addEventListener('touchend', (e) => {
            const now = Date.now();
            if (now - lastTouchEnd <= 300) {
                e.preventDefault();
            }
            lastTouchEnd = now;
        }, false);

        // ===== Keyboard Shortcuts =====
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && previewSection.style.display !== 'none') {
                newBtn.click();
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/remove-bg', methods=['POST'])
def remove_bg():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400

        file = request.files['image']

        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Check file size
        file.seek(0, os.SEEK_END)
        file_length = file.tell()
        file.seek(0)

        if file_length > 16 * 1024 * 1024:
            return jsonify({'error': 'File size exceeds 16MB limit'}), 400

        # Read and process image
        input_image = Image.open(file.stream)

        # Convert to RGB if necessary
        if input_image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', input_image.size, (255, 255, 255))
            if input_image.mode == 'P':
                input_image = input_image.convert('RGBA')
            if input_image.mode in ('RGBA', 'LA'):
                background.paste(input_image, mask=input_image.split()[-1])
                input_image = background
        elif input_image.mode != 'RGB':
            input_image = input_image.convert('RGB')

        # Remove background using rembg (OPEN SOURCE - NO API)
        output_image = remove(input_image)

        # Ensure RGBA mode
        if output_image.mode != 'RGBA':
            output_image = output_image.convert('RGBA')

        # Save to bytes with high quality
        img_io = io.BytesIO()
        output_image.save(img_io, format='PNG', optimize=True)
        img_io.seek(0)

        return send_file(
            img_io,
            mimetype='image/png',
            as_attachment=False
        )

    except Exception as e:
        return jsonify({'error': f'Processing error: {str(e)}'}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    print("=" * 60)
    print("BG Remover Pro - Perfect Version")
    print("=" * 60)
    print("Local: http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
