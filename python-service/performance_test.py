#!/usr/bin/env python3
"""
Performance test script for the high-performance PDF service.
This script will test concurrent PDF generation to demonstrate the speed improvements.
"""

import time
import asyncio
import aiohttp
import argparse

from typing import List, Dict

class PDFServiceTester:
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def generate_pdf(self, url: str) -> Dict:
        """Submit a PDF generation request"""
        async with self.session.post(
            f"{self.base_url}/generate_pdf",
            json={"url": url}
        ) as response:
            result = await response.json()
            result['submit_time'] = time.time()
            return result

    async def check_status(self, task_id: str) -> Dict:
        """Check the status of a PDF generation task"""
        async with self.session.get(
            f"{self.base_url}/pdf_status/{task_id}"
        ) as response:
            return await response.json()

    async def wait_for_completion(self, task_id: str, timeout: int = 60) -> Dict:
        """Wait for a PDF generation task to complete"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            status = await self.check_status(task_id)

            if status.get('status') in ['completed', 'failed']:
                return status

            await asyncio.sleep(0.5)

        raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")

    async def get_stats(self) -> Dict:
        """Get service statistics"""
        async with self.session.get(f"{self.base_url}/stats") as response:
            return await response.json()

    async def get_health(self) -> Dict:
        """Get service health"""
        async with self.session.get(f"{self.base_url}/health") as response:
            return await response.json()

async def run_performance_test(
    tester: PDFServiceTester,
    test_urls: List[str],
    concurrent_requests: int = 10
) -> Dict:
    """Run a performance test with multiple concurrent requests"""

    print(f"🚀 Starting performance test with {concurrent_requests} concurrent requests")
    print(f"📄 Testing {len(test_urls)} different URLs")

    initial_stats = await tester.get_stats()
    print(f"📊 Initial stats: {initial_stats}")

    start_time = time.time()

    tasks = []
    for i in range(concurrent_requests):
        url = test_urls[i % len(test_urls)]
        task = asyncio.create_task(tester.generate_pdf(url))
        tasks.append(task)

    submit_results = await asyncio.gather(*tasks)
    submit_time = time.time() - start_time

    print(f"⚡ All {concurrent_requests} requests submitted in {submit_time:.2f}s")

    completion_tasks = []
    for result in submit_results:
        if 'task_id' in result:
            task = asyncio.create_task(tester.wait_for_completion(result['task_id']))
            completion_tasks.append(task)

    completion_results = await asyncio.gather(*completion_tasks, return_exceptions=True)
    total_time = time.time() - start_time

    successful = [r for r in completion_results if isinstance(r, dict) and r.get('status') == 'completed']
    failed = [r for r in completion_results if isinstance(r, dict) and r.get('status') == 'failed']
    timeouts = [r for r in completion_results if isinstance(r, TimeoutError)]

    processing_times = []
    for result in successful:
        if 'processing_time' in result:
            processing_times.append(result['processing_time'])

    avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0

    final_stats = await tester.get_stats()

    performance_report = {
        'test_duration': total_time,
        'submission_time': submit_time,
        'concurrent_requests': concurrent_requests,
        'successful_pdfs': len(successful),
        'failed_pdfs': len(failed),
        'timeout_pdfs': len(timeouts),
        'success_rate': len(successful) / concurrent_requests * 100,
        'average_processing_time': avg_processing_time,
        'throughput_per_second': len(successful) / total_time if total_time > 0 else 0,
        'initial_stats': initial_stats,
        'final_stats': final_stats
    }

    return performance_report

def print_performance_report(report: Dict):
    print("\n" + "="*60)
    print("🎯 PERFORMANCE TEST RESULTS")
    print("="*60)

    print(f"📊 Test Overview:")
    print(f"   • Total Duration: {report['test_duration']:.2f}s")
    print(f"   • Submission Time: {report['submission_time']:.2f}s")
    print(f"   • Concurrent Requests: {report['concurrent_requests']}")

    print(f"\n✅ Success Metrics:")
    print(f"   • Successful PDFs: {report['successful_pdfs']}")
    print(f"   • Failed PDFs: {report['failed_pdfs']}")
    print(f"   • Timeout PDFs: {report['timeout_pdfs']}")
    print(f"   • Success Rate: {report['success_rate']:.1f}%")

    print(f"\n⚡ Performance Metrics:")
    print(f"   • Average Processing Time: {report['average_processing_time']:.2f}s")
    print(f"   • Throughput: {report['throughput_per_second']:.2f} PDFs/second")

    print(f"\n🔧 Chrome Pool Performance:")
    final_stats = report['final_stats']
    chrome_pool = final_stats.get('chrome_pool', {})
    print(f"   • Available Instances: {chrome_pool.get('available_instances', 0)}")
    print(f"   • Busy Instances: {chrome_pool.get('busy_instances', 0)}")
    print(f"   • Current Total: {chrome_pool.get('current_instances', 0)}")
    print(f"   • Min Instances: {chrome_pool.get('min_instances', 3)}")
    print(f"   • Max Instances: {chrome_pool.get('max_instances', 20)}")
    print(f"   • Peak Instances: {chrome_pool.get('peak_instances', 0)}")

    print(f"\n📈 Dynamic Scaling Stats:")
    print(f"   • Scale Up Events: {chrome_pool.get('scale_up_events', 0)}")
    print(f"   • Scale Down Events: {chrome_pool.get('scale_down_events', 0)}")
    print(f"   • Average Wait Time: {chrome_pool.get('average_wait_time', 0):.2f}s")

    last_scale_up = chrome_pool.get('last_scale_up')
    last_scale_down = chrome_pool.get('last_scale_down')
    print(f"   • Last Scale Up: {last_scale_up if last_scale_up else 'Never'}")
    print(f"   • Last Scale Down: {last_scale_down if last_scale_down else 'Never'}")

    print(f"\n📈 Service Stats:")
    print(f"   • Total Tasks Processed: {final_stats.get('total_tasks', 0)}")
    print(f"   • Queue Size: {final_stats.get('queue_size', 0)}")
    print(f"   • Overall Avg Processing Time: {final_stats.get('average_processing_time', 0):.2f}s")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://localhost:5000', help='PDF service URL')
    parser.add_argument('--concurrent', type=int, default=10, help='Number of concurrent requests')
    parser.add_argument('--test-urls', nargs='+', default=[
        'https://example.com',
        'https://httpbin.org/html',
        'https://jsonplaceholder.typicode.com',
        'https://httpstat.us/200'
    ], help='URLs to test PDF generation with')

    args = parser.parse_args()

    print("🔥 HIGH-PERFORMANCE PDF SERVICE TESTER")
    print(f"🌐 Testing service at: {args.url}")

    async with PDFServiceTester(args.url) as tester:
        try:
            health = await tester.get_health()
            print(f"💚 Service Health: {health}")

            report = await run_performance_test(
                tester,
                args.test_urls,
                args.concurrent
            )

            print_performance_report(report)

        except Exception as e:
            print(f"❌ Test failed: {e}")
            return 1

    return 0

if __name__ == "__main__":
    exit(asyncio.run(main()))
