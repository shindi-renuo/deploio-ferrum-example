import os
import uuid
import logging
import threading
import asyncio

from pyppeteer import launch
from flask import Flask, request, jsonify, send_from_directory

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

PDF_DIR = os.path.abspath("pdf")
os.makedirs(PDF_DIR, exist_ok=True)
logger.info(f"PDF directory created at {PDF_DIR}")

pdf_generation_status = {}

@app.route("/pdf/<path:filename>")
def serve_pdf(filename):
    return send_from_directory(PDF_DIR, filename)

@app.route("/generate_pdf", methods=["POST"])
async def generate_pdf():
    """
    Expects JSON: { "url": "https://..." }
    Returns JSON: { "pdf_url": "/pdf/<filename>.pdf" }
    """
    body = request.json
    url = body.get("url")
    if not url:
        return jsonify({"detail": "Missing 'url' in request body"}), 400
    logger.info(f"Received request with URL: {url}")

    task_id = str(uuid.uuid4())
    pdf_generation_status[task_id] = {"status": "pending", "pdf_url": None, "error": None}

    thread = threading.Thread(target=_run_async_in_thread, args=(_generate_pdf_task(url, task_id, request.host_url),))
    thread.start()

    return jsonify({"task_id": task_id, "status": "processing"}), 202

def _run_async_in_thread(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(coro)
    loop.close()

async def _generate_pdf_task(url, task_id, host_url):
    browser = None
    try:
        browser = await launch(
            headless=True,
            executablePath='/usr/bin/chromium',
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            handleSIGINT=False,
            handleSIGTERM=False,
            handleSIGHUP=False,
        )
        logger.info("Launched Chrome in headless mode")
        page = await browser.newPage()
        logger.info("Created a new page")

        await page.goto(url, {"waitUntil": "networkidle2"})
        logger.info(f"Navigated to URL: {url}")

        filename = f"{uuid.uuid4()}.pdf"
        output_path = os.path.join(PDF_DIR, filename)
        logger.info(f"Generated filename: {filename}")

        await page.pdf({"path": output_path, "format": "A4", "margin": {
            "left": "0.5in",
            "right": "0.5in",
            "top": "0.5in",
            "bottom": "0.5in"
        }})
        logger.info(f"Saved PDF at: {output_path}")

        pdf_url = f"{host_url}pdf/{filename}"
        pdf_generation_status[task_id].update({"status": "completed", "pdf_url": pdf_url, "pdf_file_name": filename})
        logger.info(f"PDF generation for task {task_id} completed. PDF URL: {pdf_url}")

    except Exception as e:
        logger.error(f"Error generating PDF for task {task_id}: {e}")
        pdf_generation_status[task_id].update({"status": "failed", "error": str(e)})

    finally:
        if browser:
            await browser.close()
            logger.info(f"Closed browser for task {task_id}")

@app.route("/health", methods=["GET"])
def health_check():
    logger.info("Health check requested")
    return jsonify({"status": "ok"})

@app.route("/pdf_status/<task_id>", methods=["GET"])
def get_pdf_status(task_id):
    status = pdf_generation_status.get(task_id)
    if not status:
        return jsonify({"detail": "Task ID not found"}), 404
    return jsonify(status)
