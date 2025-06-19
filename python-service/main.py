# imports
import os
import uuid
import logging
import asyncio
import shutil
import hypercorn.asyncio
import asyncpg

from collections import deque
from pyppeteer import launch
from hypercorn import Config
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
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

# like interface in typescript
# we define a class for chrome instances
@dataclass
class ChromeInstance:
    browser: object
    usage_count: int = 0 # how many pdfs have been generated w/ this chrome instance
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)

    # check if it's been used more than 3 times or 10 mins have passed since created_at
    def is_expired(self) -> bool:
        """Chrome instance expires after 10 minutes or 3 uses"""
        return (
            self.usage_count >= 3 or
            datetime.now() - self.created_at > timedelta(minutes=10)
        )

    # incrementer
    def use(self):
        self.usage_count += 1
        self.last_used = datetime.now()

# dataclass to define a PDF generation task
@dataclass
class PDFTask:
    task_id: str
    status: str = "pending"
    pdf_url: Optional[str] = None # url of the generated pdf (this_server.com/pdf/...)
    pdf_file_name: Optional[str] = None # it's name
    error: Optional[str] = None # None if no errors, otherwise the error message
    created_at: datetime = field(default_factory=datetime.now) # when generation process started
    completed_at: Optional[datetime] = None # when it was completed

# Defines a Pool of chrome instances
# a pool is a collection of chrome instances, that can be re-used (min 3 times, max 20 times)
# instead of creating a new instance for every PDF generation task/request
# it also scales up and down based on the number of tasks in queue
class ChromePool:
    def __init__(self, min_instances: int = 3, max_instances: int = 20):
        self.min_instances = min_instances
        self.max_instances = max_instances
        self.available_instances: deque = deque() # how many are available to be used (excluding busi ones)
        # Dictionary to keep track of busy Chrome instances, identified by their id
        self.busy_instances: Dict[int, ChromeInstance] = {}
        # Lock for asynchronous operations to ensure thread safety
        self.lock = asyncio.Lock()

        # Metrics for tracking scaling operations
        self.scaling_metrics = {
            'scale_up_events': 0, # Counts the number of scale-up events
            'scale_down_events': 0, # Counts the number of scale-down events
            'last_scale_up': None, # Timestamp of the last scale-up event
            'last_scale_down': None, # Timestamp of the last scale-down event
            'peak_instances': min_instances, # Highest number of instances reached
            'total_wait_time': 0.0, # Total time spent waiting for instances
            'wait_count': 0 # Number of times an instance was waited for
        }

        # Thresholds for scaling decisions
        self.scale_up_threshold_queue_size = 5 # Queue size threshold for scaling up
        self.scale_up_threshold_wait_time = 2.0 # Wait time threshold for scaling up
        self.scale_down_idle_time = 300 # Idle time threshold for scaling down
        self.min_scale_interval = 30 # Minimum time between scaling operations

        # Task for managing scaling operations
        self._scaling_task = None

    async def get_instance(self) -> Tuple[object, int]:
        """Get an available Chrome instance or create a new one with dynamic scaling"""
        async with self.lock: # lock, meaning only one thread can access this at a time
            await self._cleanup_expired_instances() # remove expired instances from available pool

            if self.available_instances: # if there are available instances, use one of them
                instance = self.available_instances.popleft() # use first one
                instance_id = id(instance)
                self.busy_instances[instance_id] = instance # add to busy instances (we are using it now)
                instance.use() # increment usage => decreases life-time of instance by 1 use
                logger.info(f"Reusing Chrome instance {instance_id} (usage: {instance.usage_count}/3)")
                return instance.browser, instance_id

            # if no available instances (we would have returned already if there were)
            if len(self.busy_instances) < self.max_instances: # if we are not at max instances, create a new one
                browser = await self._create_browser()
                instance = ChromeInstance(browser=browser) # instantiate
                instance_id = id(instance)
                self.busy_instances[instance_id] = instance # replace the old instance (w/ same id) with the new one
                instance.use() # increment usage => decreases life-time of instance by 1 use

                current_total = len(self.busy_instances) + len(self.available_instances)
                if current_total > self.scaling_metrics['peak_instances']: # if more than allowed, update peak instances (initially the default, which is min_instances/3)
                    self.scaling_metrics['peak_instances'] = current_total # increase peak instances by as many as we have now while still being under max_instances, since we added a check in the beginning

                logger.info(f"Created new Chrome instance {instance_id} (total: {current_total})")
                return browser, instance_id

            await self._check_and_scale_up() # check if we should scale up

            wait_start = datetime.now()
            timeout = 10.0

            while not self.available_instances: # if no available instances, wait for one to be available
                elapsed = (datetime.now() - wait_start).total_seconds()
                if elapsed > timeout:
                    logger.error(f"Timeout waiting for Chrome instance after {timeout}s")
                    raise Exception(f"No Chrome instances available within {timeout}s timeout")

                await asyncio.sleep(0.1) # wait 100ms , can be increase/decreased latern on

            wait_time = (datetime.now() - wait_start).total_seconds()
            self.scaling_metrics['total_wait_time'] += wait_time # add to amount of time spent waiting
            self.scaling_metrics['wait_count'] += 1 # increment wait count

            instance = self.available_instances.popleft() # get first available instance
            instance_id = id(instance) # get id of instance
            self.busy_instances[instance_id] = instance # add to busy instances (we are using it now)
            instance.use() # increment usage => decreases life-time of instance by 1 use

            logger.info(f"Got Chrome instance {instance_id} after {wait_time:.2f}s wait")
            return instance.browser, instance_id

    # free up an instance, so it can be used again
    async def return_instance(self, instance_id: int):
        """Return a Chrome instance to the pool or close it if expired"""
        async with self.lock: # lock, meaning only one thread can access this at a time
            if instance_id in self.busy_instances: # if instance is busy
                instance = self.busy_instances.pop(instance_id) # remove from busy instances

                if instance.is_expired(): # if instance is expired
                    logger.info(f"Closing expired Chrome instance {instance_id} (usage: {instance.usage_count}/3)")
                    try:
                        await instance.browser.close() # quit browser
                    except Exception as e:
                        logger.error(f"Error closing Chrome instance {instance_id}: {e}") # log error
                else:
                    logger.info(f"Returning Chrome instance {instance_id} to pool")
                    self.available_instances.append(instance) # add to available instances

    async def _cleanup_expired_instances(self):
        """Remove expired instances from available pool"""
        expired_instances = [instance for instance in self.available_instances if instance.is_expired()] # list comprehension to get expired instances (i love one-liners)
        for instance in expired_instances:
            self.available_instances.remove(instance) # remove from available instances
            logger.info(f"Cleaning up expired Chrome instance")
            try:
                await instance.browser.close() # quit browser
            except Exception as e:
                logger.error(f"Error closing expired instance: {e}")

    async def _create_browser(self):
        """Create a new Chrome browser instance"""
        chromium_path = self._get_chromium_path()

        return await launch(
            headless=True,
            executablePath=chromium_path,
            args=[
                "--no-sandbox", # otherwise won't work in docker
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", # we don't need shared memory                "--disable-gpu",
                "--disable-extensions", # unnecessary
                "--disable-plugins", # what even is this, we don't need it
                "--no-first-run", # skip wizard
                "--no-default-browser-check", # don't check if chromium is default browser
                "--max_old_space_size=4096", # limit memory usage
                "--disable-background-timer-throttling", # don't throttle background tasks
                "--disable-backgrounding-occluded-windows", # don't background occluded windows
                "--disable-renderer-backgrounding" # don't background renderers
            ],
            handleSIGINT=False, # we need to add this, otherwise pyppeteer will crash (https://stackoverflow.com/a/77980538)
            handleSIGTERM=False,
            handleSIGHUP=False,
        )

    def _get_chromium_path(self):
        """Auto-detect Chromium executable path (macOS locally, linux on deploio)"""

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
            chromium_path = os.environ['CHROMIUM_PATH'] # get from env variable
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

        # happens rarely!
        logger.warning("Could not find Chromium executable, letting pyppeteer handle it")
        return None

    # runs when script is stopped (mainly when new build is being deployed)
    async def shutdown(self):
        """Close all Chrome instances"""
        if self._scaling_task and not self._scaling_task.done():
            self._scaling_task.cancel()
            try:
                await self._scaling_task
            except asyncio.CancelledError:
                pass

        async with self.lock:
            all_instances = list(self.available_instances) + list(self.busy_instances.values())
            for instance in all_instances:
                try:
                    await instance.browser.close()
                    logger.info("Closed Chrome instance during shutdown")
                except Exception as e:
                    logger.error(f"Error closing instance during shutdown: {e}")

            self.available_instances.clear()
            self.busy_instances.clear()

    async def _check_and_scale_up(self):
        """Check if we should scale up and do it if needed"""
        now = datetime.now()  # get the current time

        # check if the minimum scale interval has passed since the last scale up
        if (self.scaling_metrics['last_scale_up'] and
            (now - self.scaling_metrics['last_scale_up']).total_seconds() < self.min_scale_interval):
            return  # if not, exit the function

        current_total = len(self.busy_instances) + len(self.available_instances)  # calculate the total instances
        if current_total >= self.max_instances:  # check if we've reached the maximum instances
            logger.warning(f"Already at max instances ({self.max_instances}), cannot scale up")
            return  # if at max, exit the function

        logger.info(f"Scaling up Chrome pool from {current_total} to {current_total + 1} instances")  # log the scale up attempt
        try:
            browser = await self._create_browser()  # create a new browser instance
            instance = ChromeInstance(browser=browser)  # create a new ChromeInstance
            self.available_instances.append(instance)  # add the instance to the available pool

            self.scaling_metrics['scale_up_events'] += 1  # increment the scale up events counter
            self.scaling_metrics['last_scale_up'] = now  # update the last scale up time

            new_total = len(self.busy_instances) + len(self.available_instances)  # calculate the new total instances
            if new_total > self.scaling_metrics['peak_instances']:  # check if the new total exceeds the peak instances
                self.scaling_metrics['peak_instances'] = new_total  # update the peak instances if necessary

            logger.info(f"Successfully scaled up to {new_total} Chrome instances")  # log the successful scale up

        except Exception as e:
            logger.error(f"Failed to scale up Chrome pool: {e}")  # log any errors that occur during scale up

    async def _check_and_scale_down(self):
        """Check if we should scale down and do it if needed"""
        now = datetime.now()  # get the current time

        # check if the minimum scale interval has passed since the last scale down
        if (self.scaling_metrics['last_scale_down'] and
            (now - self.scaling_metrics['last_scale_down']).total_seconds() < self.min_scale_interval):
            return  # if not, exit the function

        current_total = len(self.busy_instances) + len(self.available_instances)  # calculate the total instances

        # check if we've reached the minimum instances
        if current_total <= self.min_instances:
            return  # if not, exit the function

        # check if there are no available instances
        if not self.available_instances:
            return  # if not, exit the function

        idle_instances = [] # list of idle instances
        for instance in self.available_instances: # iterate over available instances
            idle_time = (now - instance.last_used).total_seconds() # calculate the idle time
            if idle_time > self.scale_down_idle_time: # check if the idle time is greater than the idle time threshold
                idle_instances.append(instance) # add to list of idle instances

        if idle_instances: # if there are idle instances
            instance_to_remove = idle_instances[0] # remove the first idle instance
            self.available_instances.remove(instance_to_remove) # remove from available instances

            try:
                await instance_to_remove.browser.close() # quit browser
                logger.info(f"Scaled down Chrome pool by removing idle instance")

                self.scaling_metrics['scale_down_events'] += 1 # increment the scale down events counter
                self.scaling_metrics['last_scale_down'] = now # update the last scale down time

                new_total = len(self.busy_instances) + len(self.available_instances) # calculate the new total instances
                logger.info(f"Chrome pool scaled down to {new_total} instances")

            except Exception as e:
                logger.error(f"Error closing instance during scale down: {e}")

    async def start_scaling_monitor(self):
        """Start the background scaling monitor"""
        if self._scaling_task is None or self._scaling_task.done():
            self._scaling_task = asyncio.create_task(self._scaling_monitor_loop())
            logger.info("Started Chrome pool scaling monitor")

    async def _scaling_monitor_loop(self):
        """Background loop to monitor and scale the Chrome pool"""
        while True:
            try:
                await asyncio.sleep(10)

                async with self.lock:
                    await self._check_and_scale_down()

            except asyncio.CancelledError:
                logger.info("Chrome pool scaling monitor stopped")
                break
            except Exception as e:
                logger.error(f"Error in scaling monitor: {e}")
                await asyncio.sleep(5)

    def get_scaling_stats(self) -> Dict:
        """Get scaling statistics"""
        current_total = len(self.busy_instances) + len(self.available_instances)
        avg_wait_time = (self.scaling_metrics['total_wait_time'] / self.scaling_metrics['wait_count']
                        if self.scaling_metrics['wait_count'] > 0 else 0)

        return {
            'current_instances': current_total,
            'available_instances': len(self.available_instances),
            'busy_instances': len(self.busy_instances),
            'min_instances': self.min_instances,
            'max_instances': self.max_instances,
            'peak_instances': self.scaling_metrics['peak_instances'],
            'scale_up_events': self.scaling_metrics['scale_up_events'],
            'scale_down_events': self.scaling_metrics['scale_down_events'],
            'average_wait_time': round(avg_wait_time, 2),
            'last_scale_up': self.scaling_metrics['last_scale_up'].isoformat() if self.scaling_metrics['last_scale_up'] else None,
            'last_scale_down': self.scaling_metrics['last_scale_down'].isoformat() if self.scaling_metrics['last_scale_down'] else None
        }

chrome_pool = ChromePool(min_instances=3, max_instances=20)
task_queue = asyncio.Queue(maxsize=100) # queue for tasks

# Database connection pool
db_pool = None

async def init_database():
    """Initialize database connection pool and create tables"""
    global db_pool

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")

    try:
        db_pool = await asyncpg.create_pool(database_url, min_size=5, max_size=20)
        logger.info("Database connection pool created successfully")

        # Create tables if they don't exist
        async with db_pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS pdf_tasks (
                    task_id VARCHAR(255) PRIMARY KEY,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    pdf_url TEXT,
                    pdf_file_name VARCHAR(255),
                    error TEXT,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMP WITH TIME ZONE
                )
            ''')

            # Create an index for better query performance
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_pdf_tasks_status ON pdf_tasks(status);
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_pdf_tasks_created_at ON pdf_tasks(created_at);
            ''')

        logger.info("Database tables created/verified successfully")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

async def close_database():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database connection pool closed")

# Database operations for PDFTask
class DatabaseTaskManager:
    @staticmethod
    async def create_task(task_id: str) -> None:
        """Create a new task in the database"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO pdf_tasks (task_id, status, created_at) VALUES ($1, $2, $3)',
                task_id, 'pending', datetime.now()
            )

    @staticmethod
    async def get_task(task_id: str) -> Optional[PDFTask]:
        """Get a task by ID from the database"""
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM pdf_tasks WHERE task_id = $1', task_id
            )
            if row:
                return PDFTask(
                    task_id=row['task_id'],
                    status=row['status'],
                    pdf_url=row['pdf_url'],
                    pdf_file_name=row['pdf_file_name'],
                    error=row['error'],
                    created_at=row['created_at'],
                    completed_at=row['completed_at']
                )
            return None

    @staticmethod
    async def update_task_status(task_id: str, status: str, error: str = None) -> None:
        """Update task status in the database"""
        async with db_pool.acquire() as conn:
            if error:
                await conn.execute(
                    'UPDATE pdf_tasks SET status = $1, error = $2, completed_at = $3 WHERE task_id = $4',
                    status, error, datetime.now(), task_id
                )
            else:
                await conn.execute(
                    'UPDATE pdf_tasks SET status = $1, completed_at = $2 WHERE task_id = $3',
                    status, datetime.now(), task_id
                )

    @staticmethod
    async def complete_task(task_id: str, pdf_url: str, pdf_file_name: str) -> None:
        """Mark task as completed with PDF details"""
        async with db_pool.acquire() as conn:
            await conn.execute(
                'UPDATE pdf_tasks SET status = $1, pdf_url = $2, pdf_file_name = $3, completed_at = $4 WHERE task_id = $5',
                'completed', pdf_url, pdf_file_name, datetime.now(), task_id
            )

    @staticmethod
    async def get_tasks_by_status(status: str) -> List[PDFTask]:
        """Get all tasks with a specific status"""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT * FROM pdf_tasks WHERE status = $1', status
            )
            return [
                PDFTask(
                    task_id=row['task_id'],
                    status=row['status'],
                    pdf_url=row['pdf_url'],
                    pdf_file_name=row['pdf_file_name'],
                    error=row['error'],
                    created_at=row['created_at'],
                    completed_at=row['completed_at']
                ) for row in rows
            ]

    @staticmethod
    async def get_task_stats() -> Dict:
        """Get task statistics from the database"""
        async with db_pool.acquire() as conn:
            # Get counts by status
            stats = await conn.fetchrow('''
                SELECT
                    COUNT(*) as total_tasks,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_tasks,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_tasks,
                    COUNT(CASE WHEN status IN ('queued', 'processing') THEN 1 END) as active_tasks
                FROM pdf_tasks
            ''')

            # Get average processing time for completed tasks
            avg_time = await conn.fetchval('''
                SELECT AVG(EXTRACT(EPOCH FROM (completed_at - created_at)))
                FROM pdf_tasks
                WHERE status = 'completed' AND completed_at IS NOT NULL
            ''')

            return {
                'total_tasks': stats['total_tasks'],
                'completed_tasks': stats['completed_tasks'],
                'failed_tasks': stats['failed_tasks'],
                'active_tasks': stats['active_tasks'],
                'average_processing_time': round(avg_time or 0, 2)
            }

    @staticmethod
    async def cleanup_old_tasks(hours: int = 24) -> int:
        """Delete old completed tasks older than specified hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        async with db_pool.acquire() as conn:
            result = await conn.execute(
                'DELETE FROM pdf_tasks WHERE completed_at < $1 AND status IN ($2, $3)',
                cutoff_time, 'completed', 'failed'
            )
            # Extract number from result string like "DELETE 5"
            return int(result.split()[-1]) if result.split()[-1].isdigit() else 0

# background worker to process PDF generation tasks
async def pdf_worker():
    while True:
        try:
            task_id, url, host_url = await task_queue.get()
            await _generate_pdf_task(url, task_id, host_url)
            task_queue.task_done()
        except Exception as e:
            logger.error(f"Error in PDF worker: {e}")

async def _generate_pdf_task(url: str, task_id: str, host_url: str):
    """Generate PDF with connection pooling"""
    browser = None
    instance_id = None

    try:
        await DatabaseTaskManager.update_task_status(task_id, "processing")

        browser, instance_id = await chrome_pool.get_instance()
        logger.info(f"Processing PDF task {task_id} with Chrome instance {instance_id}")

        page = await browser.newPage()

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

        await page.close()

        pdf_url = f"{host_url}pdf/{filename}"
        await DatabaseTaskManager.complete_task(task_id, pdf_url, filename)

        # Get task to calculate processing time
        task = await DatabaseTaskManager.get_task(task_id)
        processing_time = (task.completed_at - task.created_at).total_seconds()
        logger.info(f"PDF task {task_id} completed in {processing_time:.2f}s")

    except Exception as e:
        logger.error(f"Error generating PDF for task {task_id}: {e}")
        await DatabaseTaskManager.update_task_status(task_id, "failed", str(e))

    finally:
        if instance_id:
            await chrome_pool.return_instance(instance_id)

@app.route("/pdf/<path:filename>")
async def serve_pdf(filename):
    return await send_from_directory(PDF_DIR, filename)

@app.route("/generate_pdf", methods=["POST"])
async def generate_pdf():
    """
    Expects JSON: { "url": "https://..." }
    Returns JSON: { "task_id": "...", "status": "processing" }
    """
    try:
        body = await quart_request.get_json()
        url = body.get("url")
        if not url:
            return quart_jsonify({"detail": "Missing 'url' in request body"}), 400

        logger.info(f"Received PDF generation request for: {url}")

        task_id = str(uuid.uuid4())
        await DatabaseTaskManager.create_task(task_id)

        try:
            host_url = f"{quart_request.scheme}://{quart_request.host}/"
            await task_queue.put((task_id, url, host_url))
            logger.info(f"Queued PDF task {task_id}")

            return quart_jsonify({
                "task_id": task_id,
                "status": "queued",
                "queue_size": task_queue.qsize()
            }), 202

        except asyncio.QueueFull:
            # Clean up the database entry if queue is full
            async with db_pool.acquire() as conn:
                await conn.execute('DELETE FROM pdf_tasks WHERE task_id = $1', task_id)
            return quart_jsonify({"detail": "Server too busy, please try again later"}), 503

    except Exception as e:
        logger.error(f"Error in generate_pdf endpoint: {e}")
        return quart_jsonify({"detail": "Internal server error"}), 500

@app.route("/pdf_status/<task_id>", methods=["GET"])
async def get_pdf_status(task_id):
    task = await DatabaseTaskManager.get_task(task_id)
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
    total_instances = len(chrome_pool.available_instances) + len(chrome_pool.busy_instances)

    # Get active tasks from database
    processing_tasks = await DatabaseTaskManager.get_tasks_by_status("processing")

    return quart_jsonify({
        "status": "ok",
        "active_tasks": len(processing_tasks),
        "queue_size": task_queue.qsize(),
        "chrome_instances": {
            "available": len(chrome_pool.available_instances),
            "busy": len(chrome_pool.busy_instances),
            "total": total_instances,
            "min": chrome_pool.min_instances,
            "max": chrome_pool.max_instances
        }
    })

@app.route("/stats", methods=["GET"])
async def get_stats():
    """Get performance statistics with dynamic scaling info"""
    # Get statistics from database
    task_stats = await DatabaseTaskManager.get_task_stats()
    scaling_stats = chrome_pool.get_scaling_stats()

    return quart_jsonify({
        "total_tasks": task_stats["total_tasks"],
        "completed_tasks": task_stats["completed_tasks"],
        "failed_tasks": task_stats["failed_tasks"],
        "active_tasks": task_stats["active_tasks"],
        "queue_size": task_queue.qsize(),
        "average_processing_time": task_stats["average_processing_time"],
        "chrome_pool": scaling_stats
    })

@app.before_serving
async def startup():
    """Start background workers"""
    logger.info("Starting PDF service with dynamic scaling architecture")

    # Initialize database connection
    await init_database()

    for i in range(3):
        asyncio.create_task(pdf_worker())
        logger.info(f"Started PDF worker {i+1}")

    asyncio.create_task(cleanup_old_tasks())
    logger.info("Started cleanup task")

    await chrome_pool.start_scaling_monitor()
    logger.info("Started Chrome pool scaling monitor")

@app.after_serving
async def shutdown():
    """Cleanup resources"""
    logger.info("Shutting down PDF service")
    await chrome_pool.shutdown()
    await close_database()

async def cleanup_old_tasks():
    """Cleanup old completed tasks to prevent memory leaks"""
    while True:
        try:
            # Clean up tasks older than 1 hour
            deleted_count = await DatabaseTaskManager.cleanup_old_tasks(hours=1)

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old tasks")

            await asyncio.sleep(300)  # Run every 5 minutes

        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    config = Config()
    config.bind = ["0.0.0.0:5000"]
    config.workers = 1
    config.worker_class = "asyncio"
    config.accesslog = "-"
    config.errorlog = "-"
    config.loglevel = "info"

    logger.info("Starting high-performance PDF service on port 5000")
    asyncio.run(hypercorn.asyncio.serve(app, config))
