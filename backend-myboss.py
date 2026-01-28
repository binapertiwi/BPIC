from flask import Flask, request, jsonify                      # ⬅️ Import Flask untuk membuat API
import os, requests                                            # ⬅️ Import os dan requests untuk operasi sistem dan HTTP
from pathlib import Path                                       # ⬅️ Untuk menangani path file
import google.generativeai as genai                            # ⬅️ Import Google Gemini API

app = Flask(__name__)                                          # ⬅️ Inisialisasi aplikasi Flask

# === Konfigurasi API Gemini ===
GENAI_API_KEY = "AIzaSyATPClmu9eskQapcO1HyBT77701aRlybC0"      # ⬅️ API Key Gemini (seharusnya disimpan aman)
genai.configure(api_key=GENAI_API_KEY)                         # ⬅️ Konfigurasi API Key untuk Gemini

# === Fungsi untuk memproses prompt dan file PDF dengan Gemini ===
def process_with_gemini(full_prompt, pdf_paths=None):
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")      # ⬅️ Gunakan model Gemini versi flash

        parts = [{"text": full_prompt}]                        # ⬅️ Tambahkan prompt ke parts
        if pdf_paths:                                          # ⬅️ Jika ada file PDF disediakan
            for path in pdf_paths:
                if path.exists():
                    with open(path, "rb") as file:             # ⬅️ Baca file PDF sebagai biner
                        parts.append({
                            "inline_data": {
                                "mime_type": "application/pdf",# ⬅️ Format yang dikenali Gemini
                                "data": file.read()
                            }
                        })

        response = model.generate_content([{"parts": parts}])  # ⬅️ Kirim prompt + PDF ke Gemini
        return response.text.strip()                           # ⬅️ Kembalikan hasil teks dari Gemini

    except Exception as e:
        return f"Error saat proses Gemini: {e}"                # ⬅️ Tangani jika ada error saat proses

    finally:
        if pdf_paths:                                          # ⬅️ Hapus file PDF lokal setelah proses
            for path in pdf_paths:
                if path.exists():
                    try:
                        path.unlink()
                    except Exception:
                        pass

# === Endpoint utama Flask untuk menerima permintaan ===
@app.route('/upload', methods=['POST'])
def upload_file():
    data = request.json                                        # ⬅️ Ambil JSON dari body request
    subject = data.get("Subject", "Tidak ada subjek")          # ⬅️ Ambil subjek email
    note = data.get("Note", "")                                # ⬅️ Ambil catatan/tautan meeting
    email_content = data.get("EmailContent", "")               # ⬅️ Ambil isi email
    files = data.get("Files", [])                              # ⬅️ Ambil daftar URL file PDF
    prompt_ai = data.get('prompt_ai')                          # ⬅️ Ambil prompt AI dari user

    try:
        # 1. Susun prompt akhir
        full_prompt = (
            f"{prompt_ai}:\n"
            f"Subjek: {subject}\n"
            f"Catatan/Link Meeting: {note}\n"
            f"Isi Email:\n{email_content}\n"
        )

        downloaded_paths = []                                  # ⬅️ Untuk menyimpan path file yang didownload

        # 2. Unduh file dari URL (jika ada)
        if files:
            media = Path("media")                              # ⬅️ Buat folder media
            media.mkdir(exist_ok=True)
            for idx, file_url in enumerate(files):             # ⬅️ Loop untuk semua file yang dikirim
                file_response = requests.get(file_url)
                if file_response.ok:
                    file_path = media / f"temp_{idx}.pdf"      # ⬅️ Simpan file sementara
                    with open(file_path, "wb") as f:
                        f.write(file_response.content)
                    downloaded_paths.append(file_path)         # ⬅️ Tambahkan ke daftar file

        # 3. Kirim prompt + PDF ke Gemini
        gemini_result = process_with_gemini(
            full_prompt,
            pdf_paths=downloaded_paths if downloaded_paths else None
        )

        # 4. Kembalikan hasil ke user
        return jsonify({
            'status': 200,
            'gemini_result': gemini_result
        }), 200

    except Exception as e:                                     # ⬅️ Tangani error umum
        return jsonify({
            'status': 500,
            'error': f'Internal error: {str(e)}'
        }), 500

# === Untuk Google Cloud Function ===
def upload(request):                                           # ⬅️ Bungkus agar dapat dipakai di Cloud Function
    with app.app_context():
        return upload_file()
