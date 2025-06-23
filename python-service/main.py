# imports
import os
import uuid
import logging
import asyncio
import shutil
from pyppeteer import launch
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, field
# flask alternative, which is asyncio compatible
from quart import Quart, request as quart_request, jsonify as quart_jsonify, send_from_directory

# set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Quart(__name__)

# create pdf dir if it doesn't exist yet
PDF_DIR = os.path.abspath("pdf")
os.makedirs(PDF_DIR, exist_ok=True)
logger.info(f"PDF directory created at {PDF_DIR}")

# Simple task storage
@dataclass
class PDFTask:
    task_id: str
    status: str = "pending"
    pdf_url: Optional[str] = None
    pdf_file_name: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

# In-memory task storage
tasks: Dict[str, PDFTask] = {}

# Global browser instance
browser = None

def _get_chromium_path():
    """Auto-detect Chromium executable path"""
    # possible paths to chromium executable
    possible_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/opt/homebrew/bin/chromium',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Chromium.app/Contents/MacOS/Chromium',
    ]

    # if we have a custom path, use it
    if 'CHROMIUM_PATH' in os.environ:
        chromium_path = os.environ['CHROMIUM_PATH']
        if os.path.exists(chromium_path):
            logger.info(f"Using Chromium from environment variable: {chromium_path}")
            return chromium_path

    # if not, try to find it in PATH
    for cmd in ['chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable']:
        path = shutil.which(cmd)
        if path:
            logger.info(f"Found Chromium in PATH: {path}")
            return path

    # if not, try to find it in possible paths
    for path in possible_paths:
        if os.path.exists(path):
            logger.info(f"Found Chromium at: {path}")
            return path

    logger.warning("Could not find Chromium executable, letting pyppeteer handle it")
    return None

async def init_browser():
    """Initialize the global browser instance"""
    global browser
    if browser is None:
        chromium_path = _get_chromium_path()
        browser = await launch(
            headless=True,
            executablePath=chromium_path,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-plugins",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            handleSIGINT=False,
            handleSIGTERM=False,
            handleSIGHUP=False,
        )
        logger.info("Browser instance initialized")

async def generate_pdf_with_context(url: str, task_id: str, host_url: str):
    """PDF generation using pyppeteer's built-in browser contexts"""
    context = None
    try:
        # Update task status
        tasks[task_id].status = "processing"

        # Ensure browser is initialized
        await init_browser()

        # Create a new incognito browser context for this task
        context = await browser.createIncognitoBrowserContext()
        logger.info(f"Created new browser context for task {task_id}")

        # Create a new page in this context
        page = await context.newPage()

        await page.setViewport({'width': 1024, 'height': 768})
        await page.setUserAgent('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36')

        await page.goto(url, {
            "waitUntil": "domcontentloaded",
            "timeout": 30000
        })
        logger.info(f"Navigated to URL: {url}")

        filename = f"{uuid.uuid4()}.pdf"
        output_path = os.path.join(PDF_DIR, filename)

        await page.pdf({
            "path": output_path,
            "format": "A4",
            "margin": {
                "left": "0.5in",
                "right": "0.5in",
                "top": "0.5in",
                "bottom": "0.5in"
            },
            "printBackground": False,
            "preferCSSPageSize": True
        })
        logger.info(f"Generated PDF: {filename}")

        pdf_url = f"{host_url}pdf/{filename}"

        # Update task with success
        tasks[task_id].status = "completed"
        tasks[task_id].pdf_url = pdf_url
        tasks[task_id].pdf_file_name = filename
        tasks[task_id].completed_at = datetime.now()

        processing_time = (tasks[task_id].completed_at - tasks[task_id].created_at).total_seconds()
        logger.info(f"PDF task {task_id} completed in {processing_time:.2f}s")

    except Exception as e:
        logger.error(f"Error generating PDF for task {task_id}: {e}")
        tasks[task_id].status = "failed"
        tasks[task_id].error = str(e)
        tasks[task_id].completed_at = datetime.now()
    finally:
        # Always close the browser context (this cleans up all pages in the context)
        if context:
            await context.close()
            logger.info(f"Closed browser context for task {task_id}")

@app.route("/pdf/<path:filename>")
async def serve_pdf(filename):
    return await send_from_directory(PDF_DIR, filename)

@app.route("/generate_pdf", methods=["POST"])
async def generate_pdf():
    """
    Expects JSON: { "url": "https://..." }
    Returns JSON: { "task_id": "...", "status": "queued" }
    """
    try:
        body = await quart_request.get_json()
        url = body.get("url")
        if not url:
            return quart_jsonify({"detail": "Missing 'url' in request body"}), 400

        logger.info(f"Received PDF generation request for: {url}")

        task_id = str(uuid.uuid4())
        task = PDFTask(task_id=task_id, status="queued")
        tasks[task_id] = task

        host_url = f"{quart_request.scheme}://{quart_request.host}/"

        # Process PDF generation in the background
        asyncio.create_task(generate_pdf_with_context(url, task_id, host_url))

        logger.info(f"Queued PDF task {task_id}")

        return quart_jsonify({
            "task_id": task_id,
            "status": "queued"
        }), 202

    except Exception as e:
        logger.error(f"Error in generate_pdf endpoint: {e}")
        return quart_jsonify({"detail": "Internal server error"}), 500

@app.route("/pdf_status/<task_id>", methods=["GET"])
async def get_pdf_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return quart_jsonify({"detail": "Task ID not found"}), 404

    response = {
        "task_id": task.task_id,
        "status": task.status,
        "created_at": task.created_at.isoformat()
    }

    if task.pdf_url:
        response["pdf_url"] = task.pdf_url
        response["pdf_file_name"] = task.pdf_file_name

    if task.error:
        response["error"] = task.error

    if task.completed_at:
        response["completed_at"] = task.completed_at.isoformat()
        response["processing_time"] = (task.completed_at - task.created_at).total_seconds()

    return quart_jsonify(response)

@app.route("/health", methods=["GET"])
async def health_check():
    active_tasks = len([task for task in tasks.values() if task.status == "processing"])

    return quart_jsonify({
        "status": "ok",
        "active_tasks": active_tasks,
        "total_tasks": len(tasks)
    })

@app.route("/stats", methods=["GET"])
async def get_stats():
    """Get basic statistics"""
    completed_tasks = len([task for task in tasks.values() if task.status == "completed"])
    failed_tasks = len([task for task in tasks.values() if task.status == "failed"])
    active_tasks = len([task for task in tasks.values() if task.status in ["queued", "processing"]])

    # Calculate average processing time
    completed_task_times = [
        (task.completed_at - task.created_at).total_seconds()
        for task in tasks.values()
        if task.status == "completed" and task.completed_at
    ]
    avg_processing_time = sum(completed_task_times) / len(completed_task_times) if completed_task_times else 0

    return quart_jsonify({
        "total_tasks": len(tasks),
        "completed_tasks": completed_tasks,
        "failed_tasks": failed_tasks,
        "active_tasks": active_tasks,
        "average_processing_time": round(avg_processing_time, 2)
    })

@app.before_serving
async def startup():
    """Initialize browser on startup"""
    logger.info("Starting simplified PDF service with browser contexts")
    await init_browser()

@app.after_serving
async def shutdown():
    """Cleanup browser on shutdown"""
    global browser
    if browser:
        await browser.close()
        logger.info("Browser closed during shutdown")

if __name__ == "__main__":
    from hypercorn import Config
    import hypercorn.asyncio

    config = Config()
    config.bind = ["0.0.0.0:5000"]
    config.workers = 1
    config.worker_class = "asyncio"
    config.accesslog = "-"
    config.errorlog = "-"
    config.loglevel = "info"

    logger.info("Starting simplified PDF service on port 5000")
    asyncio.run(hypercorn.asyncio.serve(app, config))
