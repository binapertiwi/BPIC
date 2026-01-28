from flask import Flask, request, jsonify                 # ⬅️ Import Flask untuk membuat web API
from google.cloud import storage                          # ⬅️ Import Google Cloud Storage SDK
import os, requests                                        # ⬅️ OS untuk konfigurasi dan Requests untuk HTTP
from io import BytesIO                                     # ⬅️ Untuk membaca data biner ke dalam buffer
from pathlib import Path                                   # ⬅️ Untuk manajemen path file
import google.generativeai as genai                        # ⬅️ Import Gemini API dari Google Generative AI

app = Flask(__name__)                                      # ⬅️ Inisialisasi aplikasi Flask

# === Konfigurasi ===
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"   # ⬅️ Set file kredensial GCP
GCS_BUCKET_NAME = "external_bp_data"                                # ⬅️ Nama bucket GCS
GENAI_API_KEY = "AIzaSyATPClmu9eskQapcO1HyBT77701aRlybC0"            # ⬅️ API key Gemini (harusnya disimpan aman)

genai.configure(api_key=GENAI_API_KEY)                              # ⬅️ Konfigurasi Gemini API
storage_client = storage.Client()                                   # ⬅️ Buat client untuk GCS
bucket = storage_client.bucket(GCS_BUCKET_NAME)                     # ⬅️ Ambil bucket berdasarkan nama

# === Fungsi untuk proses PDF dengan Gemini ===
def process_pdf_with_gemini(pdf_file_path, prompt_ai):
    try:
        if pdf_file_path.exists():                                  # ⬅️ Pastikan file lokal ada
            with open(pdf_file_path, "rb") as file:
                pdf_data = file.read()                              # ⬅️ Baca isi file PDF

            pdf_content = {
                "mime_type": "application/pdf",                     # ⬅️ Format file PDF untuk dikirim ke Gemini
                "data": pdf_data
            }

            model = genai.GenerativeModel("gemini-2.5-pro")         # ⬅️ Inisialisasi model Gemini
            contents = [                                            # ⬅️ Buat isi prompt
                {"parts": [
                    {"text": "Ini adalah file PDF."},
                    pdf_content,
                    {"text": prompt_ai}
                ]}
            ]
            response_gemini = model.generate_content(contents=contents)  # ⬅️ Kirim permintaan ke Gemini
            response_text = response_gemini.text                         # ⬅️ Ambil hasil teks

            if response_text.startswith("```json"):                     # ⬅️ Bersihkan format Markdown jika ada
                response_text = response_text[len("```json"):].strip()
            if response_text.endswith("```"):
                response_text = response_text[:-len("```")].strip()

            return response_text                                       # ⬅️ Kembalikan hasil Gemini
        else:
            raise FileNotFoundError(f"File {pdf_file_path} tidak ditemukan.")
    except Exception as e:
        return f"Error saat proses Gemini: {e}"                       # ⬅️ Tangani error Gemini
    finally:
        if pdf_file_path.exists():                                    # ⬅️ Hapus file lokal setelah proses
            try:
                pdf_file_path.unlink()
            except Exception:
                pass

# === Endpoint untuk upload file dan proses Gemini ===
@app.route('/upload', methods=['POST'])
def upload_file():
    data = request.json                                              # ⬅️ Ambil data JSON dari request
    url_makalah = data.get('url_makalah')                            # ⬅️ Ambil URL file PDF
    prompt_ai = data.get('prompt_ai')                                # ⬅️ Ambil prompt untuk Gemini
    row_id = data.get('row_id')                                      # ⬅️ Ambil ID baris unik

    if not url_makalah or not prompt_ai or not row_id:               # ⬅️ Validasi input wajib
        return jsonify({
            'status': 400,
            'error': 'url_makalah, prompt_ai, dan row_id wajib disediakan'
        }), 400

    try:
        download_response = requests.get(url_makalah)                # ⬅️ Unduh file PDF dari URL
        if not download_response.ok:                                 # ⬅️ Validasi keberhasilan download
            return jsonify({
                'status': 400,
                'error': f'Gagal download file dari URL. Status: {download_response.status_code}'
            }), 400

        safe_row_id = "".join(c for c in row_id if c.isalnum() or c in ('-', '_'))  # ⬅️ Sanitasi nama file
        blob_name = f"BPIC2025/MakalahBPIC2025/{safe_row_id}.pdf"    # ⬅️ Tentukan nama dan path di GCS

        blob = bucket.blob(blob_name)                                # ⬅️ Buat objek blob GCS
        blob.upload_from_file(BytesIO(download_response.content), content_type='application/pdf')  # ⬅️ Upload
        blob.make_public()                                           # ⬅️ Buat file bisa diakses publik
        public_url = blob.public_url                                 # ⬅️ Ambil URL publik GCS

        media = Path("media")                                        # ⬅️ Buat folder `media/` jika belum ada
        media.mkdir(exist_ok=True)
        pdf_path = media / "temp.pdf"                                # ⬅️ Simpan file PDF sementara
        with open(pdf_path, "wb") as f:
            f.write(download_response.content)

        gemini_result = process_pdf_with_gemini(pdf_path, prompt_ai)  # ⬅️ Proses PDF dengan Gemini

        return jsonify({                                             # ⬅️ Kembalikan respons ke client
            'status': 200,
            'public_url': public_url,
            'gemini_result': gemini_result
        }), 200

    except requests.exceptions.RequestException as e:                # ⬅️ Tangani error HTTP
        return jsonify({
            'status': 400,
            'error': f'HTTP error: {str(e)}'
        }), 400
    except Exception as e:                                           # ⬅️ Tangani error umum
        return jsonify({
            'status': 400,
            'error': f'Internal error: {str(e)}'
        }), 400

# === Fungsi untuk digunakan sebagai Google Cloud Function ===
def upload(request):                                                 # ⬅️ Fungsi pembungkus untuk Cloud Function
    with app.app_context():
        return upload_file()
