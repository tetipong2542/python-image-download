import os
import threading
import time
import uuid
import shutil
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, send_file
from imgdownloader import WordPressImageDownloader
from urllib.parse import urlparse

app = Flask(__name__)

# กำหนดโฟลเดอร์หลักสำหรับการดาวน์โหลด
BASE_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "BulkImageDownloader")
os.makedirs(BASE_DOWNLOAD_DIR, exist_ok=True)

# สร้างโฟลเดอร์สำหรับเก็บเซสชันการดาวน์โหลด
SESSION_DOWNLOAD_DIR = os.path.join(BASE_DOWNLOAD_DIR, "sessions")
os.makedirs(SESSION_DOWNLOAD_DIR, exist_ok=True)

# ตัวแปรสำหรับเก็บสถานะการดาวน์โหลด
download_status = {
    'is_running': False,
    'total_urls': 0,
    'current_url_index': 0,
    'current_url': '',
    'found_images': 0,
    'downloaded': 0,
    'skipped': 0,
    'failed': 0,
    'logs': [],
    'output_dir': '',
    'session_id': '',
    'failed_images': [],
    'prefix': '',
    'use_numbering': False,
    'start_number': 1,
    'digits': 3
}

# ฟังก์ชันสำหรับสร้าง session ID
def generate_session_id():
    return str(uuid.uuid4())

# ฟังก์ชันตรวจสอบความปลอดภัยของเส้นทาง
def is_safe_path(path):
    # ตรวจสอบว่าเส้นทางอยู่ภายใต้โฟลเดอร์หลัก
    base_path = os.path.normpath(BASE_DOWNLOAD_DIR)
    path = os.path.normpath(path)
    return path.startswith(base_path)

# ฟังก์ชันสำหรับเพิ่ม log
def add_log(message):
    timestamp = time.strftime('%H:%M:%S')
    download_status['logs'].append(f"[{timestamp}] {message}")
    if len(download_status['logs']) > 100:  # เก็บ log ล่าสุด 100 รายการ
        download_status['logs'] = download_status['logs'][-100:]

# ฟังก์ชันสำหรับตรวจสอบว่า URL เป็น URL ของรูปภาพโดยตรงหรือไม่
def is_direct_image_url(url):
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()
    return path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))

# ฟังก์ชันสำหรับดาวน์โหลดรูปภาพในเธรดแยก
def download_images_thread(urls, output_dir, prefix='', use_numbering=False, start_number=1, digits=3):
    global downloader_instance
    
    try:
        download_status['is_running'] = True
        download_status['total_urls'] = len(urls)
        download_status['current_url_index'] = 0
        download_status['downloaded'] = 0
        download_status['skipped'] = 0
        download_status['failed'] = 0
        download_status['logs'] = []
        download_status['output_dir'] = output_dir
        download_status['failed_images'] = []
        download_status['prefix'] = prefix
        download_status['use_numbering'] = use_numbering
        download_status['start_number'] = start_number
        download_status['digits'] = digits
        
        # สร้าง instance ของ WordPressImageDownloader
        downloader_instance = WordPressImageDownloader(
            output_dir=output_dir, 
            prefix=prefix, 
            use_numbering=use_numbering,
            start_number=start_number,
            digits=digits
        )
        
        # ประมวลผลแต่ละ URL
        for i, url in enumerate(urls):
            if not url.strip():  # ข้าม URL ที่ว่าง
                continue
                
            download_status['current_url_index'] = i + 1
            download_status['current_url'] = url
            
            add_log(f"กำลังประมวลผล: {url}")
            
            # ตรวจสอบว่าเป็น URL ของรูปภาพโดยตรงหรือไม่
            if is_direct_image_url(url):
                add_log(f"พบ URL รูปภาพโดยตรง: {url}")
                success, message = downloader_instance.download_image(url)
                if success:
                    download_status['downloaded'] = downloader_instance.downloaded_count
                    add_log(f"ดาวน์โหลดสำเร็จ: {os.path.basename(url)}")
                else:
                    if "already exists" in message:
                        download_status['skipped'] = downloader_instance.skipped_count
                        add_log(f"ข้าม: {os.path.basename(url)} (มีอยู่แล้ว)")
                    else:
                        download_status['failed'] = downloader_instance.failed_count
                        add_log(f"ล้มเหลว: {os.path.basename(url)}")
            else:
                # ดึงรูปภาพจาก URL เว็บไซต์
                images = downloader_instance.extract_images_from_url(url)
                download_status['found_images'] = len(images)
                
                add_log(f"พบรูปภาพ {len(images)} รูปจาก {url}")
                
                if not images:
                    continue
                
                # ดาวน์โหลดรูปภาพแต่ละรูป
                for img_url in images:
                    success, message = downloader_instance.download_image(img_url)
                    if success:
                        download_status['downloaded'] = downloader_instance.downloaded_count
                        add_log(f"ดาวน์โหลดสำเร็จ: {os.path.basename(img_url)}")
                    else:
                        if "already exists" in message:
                            download_status['skipped'] = downloader_instance.skipped_count
                            add_log(f"ข้าม: {os.path.basename(img_url)} (มีอยู่แล้ว)")
                        else:
                            download_status['failed'] = downloader_instance.failed_count
                            add_log(f"ล้มเหลว: {os.path.basename(img_url)}")
                            # เพิ่มบรรทัดนี้เพื่อแสดง URL ที่ล้มเหลวใน log
                            add_log(f"URL ที่ล้มเหลว: {img_url}")
        
        # อัปเดตรายการรูปภาพที่ล้มเหลว
        download_status['failed_images'] = downloader_instance.failed_images
        
        add_log("การดาวน์โหลดเสร็จสิ้น")
        add_log(f"ดาวน์โหลดสำเร็จ: {download_status['downloaded']} รูป")
        add_log(f"ข้าม: {download_status['skipped']} รูป")
        add_log(f"ล้มเหลว: {download_status['failed']} รูป")
        if download_status['failed'] > 0:
            add_log(f"รูปภาพที่ล้มเหลว: {len(download_status['failed_images'])} รูป (สามารถดูและลองดาวน์โหลดใหม่ได้ที่หน้า 'ดูรูปภาพที่ดาวน์โหลด')")
        add_log(f"บันทึกรูปภาพไว้ที่: {os.path.abspath(output_dir)}")
        
    except Exception as e:
        add_log(f"เกิดข้อผิดพลาด: {str(e)}")
    finally:
        download_status['is_running'] = False

# ฟังก์ชันสำหรับดาวน์โหลดรูปภาพที่ล้มเหลวซ้ำในเธรดแยก
def retry_failed_images_thread():
    global downloader_instance
    
    try:
        if not downloader_instance or not download_status['failed_images']:
            return
        
        download_status['is_running'] = True
        download_status['current_url'] = "กำลังลองดาวน์โหลดรูปภาพที่ล้มเหลวซ้ำ"
        download_status['total_urls'] = len(download_status['failed_images'])
        download_status['current_url_index'] = 0
        
        add_log(f"กำลังลองดาวน์โหลดรูปภาพที่ล้มเหลวซ้ำ {len(download_status['failed_images'])} รูป")
        
        # ลองดาวน์โหลดรูปภาพที่ล้มเหลวซ้ำ
        failed_images, success_count, still_failed = downloader_instance.retry_failed_images()
        
        # อัปเดตสถานะ
        download_status['downloaded'] = downloader_instance.downloaded_count
        download_status['failed'] = downloader_instance.failed_count
        download_status['failed_images'] = failed_images
        download_status['current_url_index'] = download_status['total_urls']
        
        add_log(f"ลองดาวน์โหลดซ้ำเสร็จสิ้น: สำเร็จ {success_count} รูป, ยังล้มเหลว {still_failed} รูป")
        
    except Exception as e:
        add_log(f"เกิดข้อผิดพลาดในการลองดาวน์โหลดซ้ำ: {str(e)}")
    finally:
        download_status['is_running'] = False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    if download_status['is_running']:
        return jsonify({'status': 'error', 'message': 'มีการดาวน์โหลดกำลังทำงานอยู่'})
    
    # รับข้อมูลจากฟอร์ม
    urls_text = request.form.get('urls', '')
    output_dir = request.form.get('output_dir', 'downloaded_images')
    prefix = request.form.get('prefix', '')
    use_numbering = request.form.get('use_numbering') == 'on'
    start_number = int(request.form.get('start_number', '1'))
    digits = int(request.form.get('digits', '3'))
    
    # สร้าง session ID และโฟลเดอร์สำหรับเซสชันนี้
    session_id = generate_session_id()
    session_download_dir = os.path.join(SESSION_DOWNLOAD_DIR, session_id)
    
    # ตรวจสอบความปลอดภัยของเส้นทาง
    if not is_safe_path(session_download_dir):
        return jsonify({'status': 'error', 'message': 'เส้นทางไดเรกทอรีไม่ปลอดภัย'})
    
    # สร้างโฟลเดอร์สำหรับเซสชัน
    os.makedirs(session_download_dir, exist_ok=True)
    
    # แยก URL แต่ละบรรทัด
    urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
    
    if not urls:
        return jsonify({'status': 'error', 'message': 'กรุณาระบุ URL อย่างน้อย 1 รายการ'})
    
    # อัปเดตสถานะการดาวน์โหลด
    download_status.update({
        'is_running': True,
        'total_urls': len(urls),
        'current_url_index': 0,
        'downloaded': 0,
        'skipped': 0,
        'failed': 0,
        'logs': [],
        'output_dir': session_download_dir,
        'session_id': session_id,
        'failed_images': [],
        'prefix': prefix,
        'use_numbering': use_numbering,
        'start_number': start_number,
        'digits': digits
    })
    
    # เริ่มเธรดสำหรับดาวน์โหลด
    thread = threading.Thread(
        target=download_images_thread, 
        args=(urls, session_download_dir, prefix, use_numbering, start_number, digits)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'status': 'success', 
        'message': 'เริ่มการดาวน์โหลด', 
        'session_id': session_id
    })

@app.route('/retry_failed_images', methods=['POST'])
def retry_failed_images():
    global downloader_instance
    
    if downloader_instance is None:
        return jsonify({"status": "error", "message": "ไม่มีการดาวน์โหลดที่ผ่านมา"}), 400
    
    # เรียกเมธอดลองดาวน์โหลดซ้ำ
    downloader_instance.retry_failed_images()
    
    # อัปเดตสถานะการดาวน์โหลด
    download_status['downloaded'] = downloader_instance.downloaded_count
    download_status['failed'] = len(downloader_instance.failed_images)
    download_status['skipped'] = downloader_instance.skipped_count
    
    return jsonify({
        "status": "success", 
        "downloaded": downloader_instance.downloaded_count,
        "failed": len(downloader_instance.failed_images),
        "skipped": downloader_instance.skipped_count
    })

@app.route('/status')
def status():
    return jsonify(download_status)

@app.route('/images/<path:filename>')
def download_file(filename):
    return send_from_directory(download_status['output_dir'], filename)

@app.route('/browse')
def browse():
    if not download_status['output_dir'] or not os.path.exists(download_status['output_dir']):
        return render_template('browse.html', images=[], output_dir='', failed_images=[])
    
    # ดึงรายการรูปภาพในโฟลเดอร์
    images = []
    for filename in os.listdir(download_status['output_dir']):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            images.append(filename)
    
    # ส่งรายการรูปภาพที่ล้มเหลวไปด้วย
    failed_images = []
    if 'failed_images' in download_status and download_status['failed_images']:
        failed_images = download_status['failed_images']
    
    return render_template('browse.html', images=images, output_dir=download_status['output_dir'], failed_images=failed_images)

@app.route('/select_directory', methods=['GET'])
def select_directory():
    # ส่งรายการไดเรกทอรีหลักที่ผู้ใช้มักใช้งาน
    default_dirs = [
        BASE_DOWNLOAD_DIR,
        os.path.join(os.path.expanduser("~"), 'Downloads'),
        os.path.join(os.path.expanduser("~"), 'Documents'),
        os.path.join(os.path.expanduser("~"), 'Pictures'),
        os.path.join(os.path.expanduser("~"), 'Desktop')
    ]
    
    # กรองเฉพาะไดเรกทอรีที่มีอยู่จริง
    existing_dirs = [d for d in default_dirs if os.path.exists(d)]
    
    return jsonify({
        'status': 'success', 
        'directories': existing_dirs
    })

@app.route('/download_zip/<session_id>', methods=['GET'])
def download_zip(session_id):
    # ตรวจสอบความปลอดภัยของ session ID
    session_path = os.path.join(SESSION_DOWNLOAD_DIR, session_id)
    
    if not os.path.exists(session_path):
        return jsonify({'status': 'error', 'message': 'เซสชันการดาวน์โหลดไม่ถูกต้อง'})
    
    # สร้างไฟล์ ZIP
    zip_filename = f'downloaded_images_{session_id}.zip'
    zip_path = os.path.join(BASE_DOWNLOAD_DIR, zip_filename)
    
    # บีบอัดโฟลเดอร์เป็น ZIP
    shutil.make_archive(zip_path[:-4], 'zip', session_path)
    
    # ส่งไฟล์ ZIP ให้ดาวน์โหลด
    return send_file(zip_path, as_attachment=True, download_name=zip_filename)

if __name__ == '__main__':
    app.run(debug=True, port=5001)  # เปลี่ยนจากพอร์ต 5000 เป็น 5001