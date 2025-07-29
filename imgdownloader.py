import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, unquote
import concurrent.futures
import argparse
from tqdm import tqdm

class WordPressImageDownloader:
    def __init__(self, output_dir="downloaded_images", prefix="", use_numbering=False, start_number=1, digits=3):
        self.output_dir = output_dir
        self.prefix = prefix  # เพิ่มตัวแปรสำหรับ prefix
        self.use_numbering = use_numbering  # ใช้การรันตัวเลขหรือไม่
        self.current_number = start_number  # ตัวเลขเริ่มต้น
        self.digits = digits  # จำนวนหลักของตัวเลข (เช่น 3 หลักจะเป็น 001, 002, ...)
        self.downloaded_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.failed_images = []  # เพิ่มรายการเก็บ URL ของรูปภาพที่ล้มเหลว
        
        # สร้างโฟลเดอร์สำหรับเก็บรูปภาพ
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
    
    def extract_images_from_url(self, url):
        """ดึงรูปภาพทั้งหมดจาก URL"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ค้นหารูปภาพทั้งหมดในหน้าเว็บ
            images = []
            
            # ค้นหาจาก <img> tags
            for img in soup.find_all('img'):
                img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if img_url:
                    # แปลง URL ให้เป็น absolute URL
                    img_url = urljoin(url, img_url)
                    images.append(img_url)
            
            # ค้นหาจาก WordPress media library (wp-content/uploads)
            wp_images = re.findall(r'https?://[^\s\'\"]+wp-content/uploads[^\s\'\"]+\.(jpg|jpeg|png|gif)', response.text)
            for match in wp_images:
                img_url = match[0]
                if img_url not in images:
                    images.append(img_url)
            
            # กรองเฉพาะรูปภาพที่มาจาก WordPress (wp-content)
            wp_images = [img for img in images if 'wp-content' in img]
            
            return wp_images
        except Exception as e:
            print(f"Error extracting images from {url}: {e}")
            return []
    
    def validate_image_url(self, img_url):
        """ตรวจสอบความถูกต้องของ URL รูปภาพ"""
        try:
            # ตรวจสอบ URL ว่าเป็นลิงค์รูปภาพที่ถูกต้อง
            if not img_url or not isinstance(img_url, str):
                return False
            
            # ตรวจสอบโดเมน
            parsed_url = urlparse(img_url)
            if not parsed_url.netloc or 'jas2015.com' not in parsed_url.netloc:
                print(f"คำเตือน: โดเมนที่ไม่คาดหวัง: {parsed_url.netloc}")
                return False
            
            # ตรวจสอบนามสกุลไฟล์
            file_ext = os.path.splitext(parsed_url.path)[1].lower()
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
            if not file_ext or file_ext not in valid_extensions:
                print(f"คำเตือน: นามสกุลไฟล์ไม่ถูกต้อง: {file_ext}")
                return False
            
            return True
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการตรวจสอบ URL: {e}")
            return False

    def download_image(self, img_url):
        """ดาวน์โหลดรูปภาพจาก URL"""
        max_retries = 3
        retry_delay = 2  # 2 วินาที

        # บันทึก URL ต้นฉบับ
        original_url = img_url

        # ถอดรหัส URL เพื่อแก้ปัญหาการเข้ารหัส
        try:
            img_url = unquote(img_url)
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการถอดรหัส URL: {e}")

        # ตรวจสอบ URL ก่อนดาวน์โหลด
        if not self.validate_image_url(img_url):
            print(f"URL ไม่ถูกต้อง: {img_url}")
            if original_url in self.failed_images:
                self.failed_images.remove(original_url)
            return False, f"URL ไม่ถูกต้อง: {img_url}"

        for attempt in range(max_retries):
            try:
                # สร้างชื่อไฟล์จาก URL
                parsed_url = urlparse(img_url)
                filename = os.path.basename(parsed_url.path)
                
                # เพิ่ม prefix และตัวเลขถ้ามีการกำหนด
                if self.use_numbering and self.prefix:
                    number_str = str(self.current_number).zfill(self.digits)
                    filename = f"{self.prefix}{number_str}_{filename}"
                    self.current_number += 1
                elif self.prefix:
                    filename = f"{self.prefix}{filename}"
                
                # ตรวจสอบว่ามีไฟล์อยู่แล้วหรือไม่
                filepath = os.path.join(self.output_dir, filename)
                if os.path.exists(filepath):
                    self.skipped_count += 1
                    return False, f"ข้าม: {filename} (มีอยู่แล้ว)"
                
                # ดาวน์โหลดรูปภาพ
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'image/webp,*/*',
                    'Accept-Language': 'th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Referer': 'https://jas2015.com/'
                }
                response = requests.get(img_url, headers=headers, stream=True, timeout=15)
                response.raise_for_status()
                
                # ตรวจสอบประเภท Content
                content_type = response.headers.get('Content-Type', '').lower()
                if not content_type.startswith('image/'):
                    print(f"คำเตือน: ประเภท Content ไม่ใช่รูปภาพ: {content_type}")
                    return False, f"ไม่ใช่รูปภาพ: {content_type}"
                
                # บันทึกไฟล์
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                self.downloaded_count += 1
                
                # ถ้าเคยล้มเหลวและตอนนี้ดาวน์โหลดสำเร็จ ให้ลบออกจากรายการล้มเหลว
                if original_url in self.failed_images:
                    self.failed_images.remove(original_url)
                    
                return True, f"ดาวน์โหลดสำเร็จ: {filename}"
            
            except requests.exceptions.RequestException as e:
                # ถ้ายังไม่ใช่การพยายามครั้งสุดท้าย ให้รอและลองใหม่
                print(f"พบข้อผิดพลาดในการดาวน์โหลด (ครั้งที่ {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    continue
                
                # ถ้าพยายามครบ 3 ครั้งแล้ว
                self.failed_count += 1
                # เพิ่ม URL ที่ล้มเหลวเข้าไปในรายการ
                if original_url not in self.failed_images:
                    self.failed_images.append(original_url)
                return False, f"ล้มเหลวหลังจากพยายาม {max_retries} ครั้ง: {original_url} - {str(e)}"
    
    def process_url(self, url):
        """ประมวลผล URL เพื่อดึงและดาวน์โหลดรูปภาพ"""
        print(f"\nProcessing: {url}")
        images = self.extract_images_from_url(url)
        print(f"Found {len(images)} images from {url}")
        
        if not images:
            return
        
        # ดาวน์โหลดรูปภาพด้วย progress bar
        with tqdm(total=len(images), desc="Downloading", unit="img") as pbar:
            for img_url in images:
                success, message = self.download_image(img_url)
                if success:
                    pbar.set_description(f"Downloaded: {os.path.basename(urlparse(img_url).path)}")
                pbar.update(1)
    
    def process_urls_from_file(self, file_path):
        """ประมวลผล URL จากไฟล์"""
        try:
            with open(file_path, 'r') as f:
                urls = [line.strip() for line in f if line.strip()]
            
            print(f"Loaded {len(urls)} URLs from {file_path}")
            
            # ประมวลผลแต่ละ URL
            for url in urls:
                self.process_url(url)
                
        except Exception as e:
            print(f"Error processing URLs from file: {e}")
    
    def process_multiple_urls(self, urls):
        """ประมวลผลหลาย URL พร้อมกัน"""
        for url in urls:
            self.process_url(url)
    
    def retry_failed_images(self):
        """พยายามดาวน์โหลดรูปภาพที่ล้มเหลวอีกครั้ง"""
        if not self.failed_images:
            print("ไม่มีรูปภาพที่ล้มเหลว")
            return
        
        print(f"\nกำลังพยายามดาวน์โหลดรูปภาพที่ล้มเหลว {len(self.failed_images)} รูป")
        
        # สร้างสำเนาของรายการรูปภาพที่ล้มเหลวเพื่อป้องกันการแก้ไขขณะวนลูป
        failed_images_copy = self.failed_images.copy()
        
        # รีเซ็ตตัวนับรูปภาพที่ล้มเหลว
        retry_failed_count = 0
        
        for img_url in failed_images_copy:
            success, message = self.download_image(img_url)
            if success:
                retry_failed_count += 1
                print(f"ดาวน์โหลดสำเร็จ: {img_url}")
            else:
                print(f"ยังคงล้มเหลว: {img_url}")
        
        print(f"\nดาวน์โหลดรูปภาพที่ล้มเหลวสำเร็จ {retry_failed_count} รูป")
    
    def show_summary(self):
        """แสดงสรุปผลการดาวน์โหลด"""
        print("\n" + "=" * 50)
        print("Download Summary:")
        print(f"Total Downloaded: {self.downloaded_count} images")
        print(f"Total Skipped: {self.skipped_count} images")
        print(f"Total Failed: {self.failed_count} images")
        if self.failed_images:
            print(f"Failed Images URLs: {len(self.failed_images)}")
        print(f"Images saved to: {os.path.abspath(self.output_dir)}")
        print("=" * 50)

def main():
    parser = argparse.ArgumentParser(description='Website Image Downloader - Extract and download images from WordPress sites')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-u', '--url', help='URL of WordPress site to download images from')
    group.add_argument('-f', '--file', help='File containing URLs of WordPress sites (one URL per line)')
    group.add_argument('-l', '--urls', nargs='+', help='Multiple WordPress URLs separated by space')
    parser.add_argument('-o', '--output', default='downloaded_images', help='Output directory for downloaded images')
    parser.add_argument('-r', '--retry', action='store_true', help='Retry failed downloads after completion')
    parser.add_argument('-p', '--prefix', default='', help='Add prefix to downloaded image filenames')
    parser.add_argument('-n', '--numbering', action='store_true', help='Use sequential numbering with prefix')
    parser.add_argument('-s', '--start', type=int, default=1, help='Starting number for sequential numbering')
    parser.add_argument('-d', '--digits', type=int, default=3, help='Number of digits for sequential numbering (e.g., 3 for 001, 002, ...)')
    
    args = parser.parse_args()
    
    downloader = WordPressImageDownloader(
        output_dir=args.output, 
        prefix=args.prefix, 
        use_numbering=args.numbering,
        start_number=args.start,
        digits=args.digits
    )
    
    if args.url:
        downloader.process_url(args.url)
    elif args.file:
        downloader.process_urls_from_file(args.file)
    elif args.urls:
        downloader.process_multiple_urls(args.urls)
    
    # ถ้ามีการระบุให้ลองดาวน์โหลดรูปภาพที่ล้มเหลวอีกครั้ง
    if args.retry and downloader.failed_images:
        print("\nRetrying failed downloads...")
        failed_images, success_count, still_failed = downloader.retry_failed_images()
        print(f"Retry results: {success_count} succeeded, {still_failed} still failed")
    
    downloader.show_summary()

if __name__ == "__main__":
    main()