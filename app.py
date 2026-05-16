from flask import Flask, render_template, request, send_file, jsonify
from rembg import remove, new_session
from PIL import Image
import io, os, img2pdf, zipfile, sqlite3, json, threading, urllib.request, urllib.error
from pdf2image import convert_from_bytes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import base64

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

os.makedirs('data', exist_ok=True)

# ─── Database ─────────────────────────────────────────────────────────────────

def get_db():
    db = sqlite3.connect('data/pixelkit.db')
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS push_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        endpoint TEXT UNIQUE NOT NULL,
        p256dh TEXT NOT NULL,
        auth TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    db.commit()
    db.close()

init_db()

# ─── VAPID Keys ───────────────────────────────────────────────────────────────

VAPID_KEYS_FILE = 'data/vapid_keys.json'

def get_or_create_vapid_keys():
    if os.path.exists(VAPID_KEYS_FILE):
        with open(VAPID_KEYS_FILE) as f:
            return json.load(f)
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ).decode()
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    pub_b64 = base64.urlsafe_b64encode(pub_bytes).decode().rstrip('=')
    keys = {'private_pem': private_pem, 'public_key': pub_b64}
    with open(VAPID_KEYS_FILE, 'w') as f:
        json.dump(keys, f)
    return keys

VAPID_KEYS = get_or_create_vapid_keys()
VAPID_PUBLIC_KEY = VAPID_KEYS['public_key']

# ─── rembg session (lazy, thread-safe) ───────────────────────────────────────

_session_lock = threading.Lock()
_bg_session = None

def get_bg_session():
    global _bg_session
    if _bg_session is None:
        with _session_lock:
            if _bg_session is None:
                try:
                    _bg_session = new_session('u2net')
                except Exception:
                    _bg_session = 'default'
    return None if _bg_session == 'default' else _bg_session

def do_remove_bg(input_bytes):
    session = get_bg_session()
    try:
        if session:
            result = remove(
                input_bytes,
                session=session,
                alpha_matting=True,
                alpha_matting_foreground_threshold=240,
                alpha_matting_background_threshold=10,
                alpha_matting_erode_size=10
            )
        else:
            result = remove(input_bytes)
    except Exception:
        if session:
            result = remove(input_bytes, session=session)
        else:
            result = remove(input_bytes)
    return result

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return render_template('index.html', vapid_public_key=VAPID_PUBLIC_KEY)

@app.route('/api/config')
def api_config():
    return jsonify({'vapidPublicKey': VAPID_PUBLIC_KEY})

# ─── Background Removal ───────────────────────────────────────────────────────

@app.route('/remove-bg', methods=['POST'])
def remove_bg():
    try:
        input_bytes = None

        # URL upload
        url = request.form.get('image_url', '').strip()
        if url:
            if not url.startswith(('http://', 'https://')):
                return jsonify({'error': 'Invalid URL. Must start with http:// or https://'}), 400
            try:
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; PixelKit/1.0)'
                })
                with urllib.request.urlopen(req, timeout=15) as resp:
                    ct = resp.headers.get('Content-Type', '')
                    if not any(t in ct for t in ['image/', 'octet-stream']):
                        return jsonify({'error': 'URL does not point to an image'}), 400
                    input_bytes = resp.read(32 * 1024 * 1024)
            except urllib.error.URLError as e:
                return jsonify({'error': f'Could not fetch URL: {str(e.reason)}'}), 400
            except Exception as e:
                return jsonify({'error': f'URL fetch failed: {str(e)}'}), 400

        # File upload
        elif 'image' in request.files:
            file = request.files['image']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            input_bytes = file.read()
        else:
            return jsonify({'error': 'No image or URL provided'}), 400

        if not input_bytes:
            return jsonify({'error': 'Empty file or URL returned no data'}), 400

        # Quick sanity check — try opening (not verify, too strict)
        try:
            Image.open(io.BytesIO(input_bytes)).load()
        except Exception:
            return jsonify({'error': 'File is not a valid image. Please use JPG, PNG, WebP, or BMP.'}), 400

        output_bytes = do_remove_bg(input_bytes)

        return send_file(
            io.BytesIO(output_bytes),
            mimetype='image/png',
            as_attachment=False,
            download_name='pixelkit_nobg.png'
        )
    except Exception as e:
        import traceback
        print(f'BG remove error: {traceback.format_exc()}')
        return jsonify({'error': 'Processing failed. Please try a different image.'}), 500

# ─── Email Subscription ───────────────────────────────────────────────────────

@app.route('/subscribe-email', methods=['POST'])
def subscribe_email():
    try:
        data = request.get_json()
        email = (data.get('email') or '').strip().lower()
        name = (data.get('name') or '').strip()
        if not email or '@' not in email or '.' not in email.split('@')[-1]:
            return jsonify({'error': 'Please enter a valid email address'}), 400
        db = get_db()
        try:
            db.execute('INSERT INTO emails (email, name) VALUES (?, ?)', (email, name))
            db.commit()
        except sqlite3.IntegrityError:
            return jsonify({'message': 'Already subscribed!', 'already': True}), 200
        finally:
            db.close()
        return jsonify({'message': 'Subscribed successfully!'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/emails')
def admin_emails():
    secret = request.args.get('secret', '')
    if secret != os.environ.get('ADMIN_SECRET', 'pixelkit-admin-2026'):
        return jsonify({'error': 'Unauthorized'}), 401
    db = get_db()
    rows = db.execute('SELECT email, name, created_at FROM emails ORDER BY created_at DESC').fetchall()
    db.close()
    return jsonify({'count': len(rows), 'emails': [dict(r) for r in rows]})

# ─── Push Notifications ───────────────────────────────────────────────────────

@app.route('/push/subscribe', methods=['POST'])
def push_subscribe():
    try:
        sub = request.get_json()
        endpoint = sub.get('endpoint')
        keys = sub.get('keys', {})
        p256dh = keys.get('p256dh', '')
        auth = keys.get('auth', '')
        if not endpoint:
            return jsonify({'error': 'Missing endpoint'}), 400
        db = get_db()
        try:
            db.execute(
                'INSERT OR REPLACE INTO push_subscriptions (endpoint, p256dh, auth) VALUES (?,?,?)',
                (endpoint, p256dh, auth)
            )
            db.commit()
        finally:
            db.close()
        return jsonify({'message': 'Subscribed to push notifications'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/push/unsubscribe', methods=['POST'])
def push_unsubscribe():
    try:
        data = request.get_json()
        endpoint = data.get('endpoint')
        if endpoint:
            db = get_db()
            db.execute('DELETE FROM push_subscriptions WHERE endpoint = ?', (endpoint,))
            db.commit()
            db.close()
        return jsonify({'message': 'Unsubscribed'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/push/count')
def push_count():
    db = get_db()
    count = db.execute('SELECT COUNT(*) as c FROM push_subscriptions').fetchone()['c']
    db.close()
    return jsonify({'count': count})

@app.route('/admin/notify', methods=['POST'])
def admin_notify():
    secret = request.args.get('secret', '')
    if secret != os.environ.get('ADMIN_SECRET', 'pixelkit-admin-2026'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        from pywebpush import webpush
        data = request.get_json() or {}
        title = data.get('title', 'PixelKit Update')
        body = data.get('body', 'New tools and features are now available!')
        url = data.get('url', '/')
        payload = json.dumps({'title': title, 'body': body, 'url': url})
        db = get_db()
        subs = db.execute('SELECT endpoint, p256dh, auth FROM push_subscriptions').fetchall()
        db.close()
        sent, failed = 0, 0
        for sub in subs:
            try:
                webpush(
                    subscription_info={'endpoint': sub['endpoint'], 'keys': {'p256dh': sub['p256dh'], 'auth': sub['auth']}},
                    data=payload,
                    vapid_private_key=VAPID_KEYS['private_pem'],
                    vapid_claims={'sub': 'mailto:admin@pixelkit.app'}
                )
                sent += 1
            except Exception:
                failed += 1
        return jsonify({'sent': sent, 'failed': failed})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── Image → PDF ──────────────────────────────────────────────────────────────

@app.route('/convert/img-to-pdf', methods=['POST'])
def img_to_pdf():
    try:
        files = request.files.getlist('images')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No images uploaded'}), 400
        img_bytes_list = []
        for file in files:
            raw = file.read()
            img = Image.open(io.BytesIO(raw)).convert('RGB')
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=92)
            buf.seek(0)
            img_bytes_list.append(buf.read())
        pdf_bytes = img2pdf.convert(img_bytes_list)
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name='pixelkit_converted.pdf')
    except Exception as e:
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 500

# ─── PDF → Images ─────────────────────────────────────────────────────────────

@app.route('/convert/pdf-to-img', methods=['POST'])
def pdf_to_img():
    try:
        if 'pdf' not in request.files:
            return jsonify({'error': 'No PDF uploaded'}), 400
        file = request.files['pdf']
        fmt = request.form.get('format', 'jpg').lower()
        if fmt not in ('jpg', 'png'):
            fmt = 'jpg'
        pdf_bytes = file.read()
        pages = convert_from_bytes(pdf_bytes, dpi=150)
        pil_fmt = 'JPEG' if fmt == 'jpg' else 'PNG'
        mime = 'image/jpeg' if fmt == 'jpg' else 'image/png'
        if len(pages) == 1:
            buf = io.BytesIO()
            pages[0].save(buf, format=pil_fmt, quality=92)
            buf.seek(0)
            return send_file(buf, mimetype=mime, as_attachment=True, download_name=f'pixelkit_page1.{fmt}')
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, page in enumerate(pages, 1):
                img_buf = io.BytesIO()
                page.save(img_buf, format=pil_fmt, quality=92)
                zf.writestr(f'page_{i}.{fmt}', img_buf.getvalue())
        zip_buf.seek(0)
        return send_file(zip_buf, mimetype='application/zip', as_attachment=True, download_name='pixelkit_pages.zip')
    except Exception as e:
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 500

# ─── Image Format Converter ───────────────────────────────────────────────────

@app.route('/convert/img-format', methods=['POST'])
def img_format_convert():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400
        file = request.files['image']
        target_fmt = request.form.get('format', 'png').lower()
        quality = max(10, min(100, int(request.form.get('quality', 92))))
        img = Image.open(file.stream)
        fmt_map = {
            'jpg': ('JPEG', 'image/jpeg', 'jpg'),
            'jpeg': ('JPEG', 'image/jpeg', 'jpg'),
            'png': ('PNG', 'image/png', 'png'),
            'webp': ('WEBP', 'image/webp', 'webp'),
            'bmp': ('BMP', 'image/bmp', 'bmp'),
            'gif': ('GIF', 'image/gif', 'gif'),
            'tiff': ('TIFF', 'image/tiff', 'tiff'),
        }
        if target_fmt not in fmt_map:
            return jsonify({'error': 'Unsupported format'}), 400
        pil_fmt, mime, ext = fmt_map[target_fmt]
        if pil_fmt in ('JPEG', 'BMP') and img.mode in ('RGBA', 'LA', 'P'):
            bg = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = bg
        elif pil_fmt == 'JPEG' and img.mode != 'RGB':
            img = img.convert('RGB')
        buf = io.BytesIO()
        save_kw = {}
        if pil_fmt == 'JPEG':
            save_kw = {'quality': quality, 'optimize': True}
        elif pil_fmt == 'WEBP':
            save_kw = {'quality': quality}
        elif pil_fmt == 'PNG':
            save_kw = {'optimize': True}
        img.save(buf, format=pil_fmt, **save_kw)
        buf.seek(0)
        name = os.path.splitext(file.filename or 'image')[0]
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=f'{name}.{ext}')
    except Exception as e:
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 500

# ─── Image Compressor ─────────────────────────────────────────────────────────

@app.route('/convert/compress', methods=['POST'])
def compress_image():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400
        file = request.files['image']
        quality = max(10, min(95, int(request.form.get('quality', 70))))
        img = Image.open(file.stream)
        fname = file.filename or 'image.jpg'
        ext = os.path.splitext(fname)[1].lower().lstrip('.')
        buf = io.BytesIO()
        if ext in ('jpg', 'jpeg'):
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(buf, format='JPEG', quality=quality, optimize=True)
            mime, out_ext = 'image/jpeg', 'jpg'
        elif ext == 'png':
            img.save(buf, format='PNG', optimize=True, compress_level=9)
            mime, out_ext = 'image/png', 'png'
        else:
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')
            img.save(buf, format='WEBP', quality=quality)
            mime, out_ext = 'image/webp', 'webp'
        buf.seek(0)
        base = os.path.splitext(fname)[0]
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=f'{base}_compressed.{out_ext}')
    except Exception as e:
        return jsonify({'error': f'Compression failed: {str(e)}'}), 500

# ─── Image Resizer ────────────────────────────────────────────────────────────

@app.route('/convert/resize', methods=['POST'])
def resize_image():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400
        file = request.files['image']
        width = request.form.get('width', type=int)
        height = request.form.get('height', type=int)
        keep_ratio = request.form.get('keep_ratio', 'true') == 'true'
        img = Image.open(file.stream)
        orig_w, orig_h = img.size
        if not width and not height:
            return jsonify({'error': 'Provide at least width or height'}), 400
        if keep_ratio:
            if width and height:
                ratio = min(width / orig_w, height / orig_h)
                width, height = int(orig_w * ratio), int(orig_h * ratio)
            elif width:
                height = int(orig_h * (width / orig_w))
            else:
                width = int(orig_w * (height / orig_h))
        width = max(1, min(8000, width or orig_w))
        height = max(1, min(8000, height or orig_h))
        img = img.resize((width, height), Image.LANCZOS)
        buf = io.BytesIO()
        fmt = 'PNG' if img.mode == 'RGBA' else 'JPEG'
        mime = 'image/png' if fmt == 'PNG' else 'image/jpeg'
        ext = 'png' if fmt == 'PNG' else 'jpg'
        save_kw = {} if fmt == 'PNG' else {'quality': 92, 'optimize': True}
        img.save(buf, format=fmt, **save_kw)
        buf.seek(0)
        name = os.path.splitext(file.filename or 'image')[0]
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=f'{name}_{width}x{height}.{ext}')
    except Exception as e:
        return jsonify({'error': f'Resize failed: {str(e)}'}), 500

# ─── Health ───────────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': '2.0'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
