from flask import Flask, request, jsonify                         # ⬅️ Import Flask untuk membuat REST API
from google.cloud import storage                                  # ⬅️ Import Google Cloud Storage client
import os, requests                                               # ⬅️ OS untuk environment & requests untuk HTTP
from io import BytesIO                                            # ⬅️ Untuk menangani data biner dari file
from pathlib import Path                                          # ⬅️ Untuk manajemen file path lokal
import google.generativeai as genai                               # ⬅️ Import Gemini dari Google Generative AI

app = Flask(__name__)                                             # ⬅️ Inisialisasi aplikasi Flask

# === Konfigurasi Environment & API Key ===
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json" # ⬅️ File kredensial GCP
GCS_BUCKET_NAME = "external_bp_data"                              # ⬅️ Nama bucket GCS (tanpa folder)
GENAI_API_KEY = "AIzaSyATPClmu9eskQapcO1HyBT77701aRlybC0"          # ⬅️ API Key Gemini (sebaiknya via env var)
USERNAME = '7000000'                                              # ⬅️ Username login BP Net
PASSWORD = 'BP654321'                                             # ⬅️ Password login BP Net

genai.configure(api_key=GENAI_API_KEY)                            # ⬅️ Konfigurasi API Gemini
storage_client = storage.Client()                                 # ⬅️ Buat client GCS
bucket = storage_client.bucket(GCS_BUCKET_NAME)                   # ⬅️ Ambil bucket sesuai nama

# === Fungsi untuk memproses PDF dengan Gemini ===
def process_pdf_with_gemini(pdf_file_path, prompt_ai):
    try:
        if pdf_file_path.exists():                                # ⬅️ Cek file lokal tersedia
            with open(pdf_file_path, "rb") as file:
                pdf_data = file.read()                            # ⬅️ Baca data PDF

            pdf_content = {
                "mime_type": "application/pdf",                   # ⬅️ Format MIME untuk PDF
                "data": pdf_data
            }

            model = genai.GenerativeModel("gemini-2.0-flash")     # ⬅️ Gunakan model Gemini versi flash
            contents = [
                {"parts": [
                    {"text": "Ini adalah file PDF."},             # ⬅️ Prompt awal
                    pdf_content,                                  # ⬅️ Data PDF
                    {"text": prompt_ai}                           # ⬅️ Prompt dari pengguna
                ]}
            ]
            response_gemini = model.generate_content(contents=contents) # ⬅️ Kirim ke Gemini
            response_text = response_gemini.text

            # Bersihkan format jika berupa kode markdown JSON
            if response_text.startswith("```json"):
                response_text = response_text[len("```json"):].strip()
            if response_text.endswith("```"):
                response_text = response_text[:-len("```")].strip()

            return response_text                                   # ⬅️ Kembalikan hasil Gemini
        else:
            raise FileNotFoundError(f"File {pdf_file_path} tidak ditemukan.")
    except Exception as e:
        return f"Error saat proses Gemini: {e}"                   # ⬅️ Tangani error Gemini
    finally:
        if pdf_file_path.exists():                                # ⬅️ Hapus file lokal setelah selesai
            try:
                pdf_file_path.unlink()
            except Exception:
                pass

# === Endpoint untuk menerima PDF dan prompt dari BP Net ===
@app.route('/upload', methods=['POST'])
def upload_file():
    data = request.json                                           # ⬅️ Ambil data JSON dari request
    download_id = data.get('download_id')                         # ⬅️ Ambil ID file dari BP Net
    prompt_ai = data.get('prompt_ai')                             # ⬅️ Prompt untuk proses Gemini

    # Validasi input wajib
    if not download_id or not prompt_ai:
        return jsonify({
            'status': 400,
            'error': 'download_id dan prompt_ai wajib disediakan'
        }), 400

    try:
        # 1. Login ke BP Net
        session = requests.Session()
        login_url = 'https://apps.binapertiwi.co.id/company/vis_structure.php?login=yes'
        login_data = {
            'AUTH_FORM': 'Y',
            'TYPE': 'AUTH',
            'backurl': '/company/vis_structure.php',
            'USER_LOGIN': USERNAME,
            'USER_PASSWORD': PASSWORD
        }
        login_response = session.post(login_url, data=login_data) # ⬅️ Kirim permintaan login

        if not (login_response.ok and "logout" in login_response.text.lower()):
            return jsonify({
                'status': 400,
                'error': 'Login ke BP Net gagal'
            }), 400

        # 2. Unduh file dari BP Net berdasarkan download_id
        download_url = f'https://apps.binapertiwi.co.id/bitrix/tools/disk/uf.php?attachedId={download_id}&action=download&ncc=1'
        download_response = session.get(download_url)             # ⬅️ Unduh file

        if not download_response.ok:                              # ⬅️ Cek jika download gagal
            return jsonify({
                'status': 400,
                'error': f'Gagal download file dari BP Net. Status: {download_response.status_code}'
            }), 400

        # 3. Upload file ke Google Cloud Storage
        blob_name = f"BPIC2025/{download_id}.pdf"                 # ⬅️ Nama path di dalam bucket
        blob = bucket.blob(blob_name)
        blob.upload_from_file(BytesIO(download_response.content)) # ⬅️ Upload dari file biner
        blob.make_public()                                       # ⬅️ Buka akses publik ke file
        public_url = blob.public_url                             # ⬅️ Dapatkan URL publik GCS

        # 4. Simpan file sementara untuk diproses oleh Gemini
        media = Path("media")
        media.mkdir(exist_ok=True)
        pdf_path = media / "temp.pdf"
        with open(pdf_path, "wb") as f:
            f.write(download_response.content)

        # 5. Proses PDF dengan Gemini
        gemini_result = process_pdf_with_gemini(pdf_path, prompt_ai)

        # 6. Kembalikan response ke client
        return jsonify({
            'status': 200,
            'public_url': public_url,
            'gemini_result': gemini_result
        }), 200

    except requests.exceptions.RequestException as e:             # ⬅️ Tangani error HTTP
        return jsonify({
            'status': 400,
            'error': f'HTTP error: {str(e)}'
        }), 400
    except Exception as e:                                        # ⬅️ Tangani error internal lainnya
        return jsonify({
            'status': 400,
            'error': f'Internal error: {str(e)}'
        }), 400

# === Fungsi untuk digunakan di Google Cloud Function ===
def upload(request):                                              # ⬅️ Bungkus endpoint untuk dipakai di GCF
    with app.app_context():
        return upload_file()
