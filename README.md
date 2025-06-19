# PDF Generator Application

A high-performance web application that converts any webpage to PDF using Python (Pyppeteer) and Ruby on Rails.

## Architecture

This application consists of two services:

1. **Python PDF Service** (`python-service/`) - Handles PDF generation using Pyppeteer
2. **Rails Web App** (`rails-app/`) - Provides the web interface and manages user interactions

## Features

- ✨ Modern, responsive web interface
- ⚡ High-performance async PDF generation
- 🔄 Real-time status updates with auto-refresh
- 📊 Connection pooling and resource management
- 🛡️ Comprehensive error handling
- 🎨 Beautiful Tailwind CSS design
- 📱 Mobile-friendly interface

## Quick Start

### Using Docker Compose (Recommended)

1. Clone this repository
2. Run the application:
   ```bash
   docker-compose up
   ```
3. Open your browser to `http://localhost:3000`

### Manual Setup

#### Python Service Setup

1. Navigate to the Python service directory:
   ```bash
   cd python-service
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Chromium (macOS with Homebrew):
   ```bash
   brew install chromium
   ```

4. Start the Python service:
   ```bash
   python main.py
   ```

The Python service will run on `http://localhost:5000`

#### Rails App Setup

1. Navigate to the Rails app directory:
   ```bash
   cd rails-app
   ```

2. Install dependencies:
   ```bash
   bundle install
   ```

3. Set the Python service URL:
   ```bash
   export PYTHON_SERVICE_URL=http://localhost:5000
   ```

4. Start the Rails server:
   ```bash
   rails server
   ```

The Rails app will run on `http://localhost:3000`

## Environment Variables

### Rails App

- `PYTHON_SERVICE_URL` - URL of the Python PDF service (default: `http://localhost:5000`)

### Python Service

The Python service uses environment-based configuration for deployment flexibility.

## API Endpoints

### Python Service

- `POST /generate_pdf` - Generate PDF from URL
- `GET /pdf_status/:task_id` - Get PDF generation status
- `GET /pdf/:filename` - Download generated PDF
- `GET /health` - Service health check
- `GET /stats` - Performance statistics

### Rails App

- `GET /` - Home page with PDF generation form
- `POST /home/generate_pdf` - Submit URL for PDF generation
- `GET /home/pdf_status` - Check PDF generation status
- `GET /home/download_pdf` - Download completed PDF

## Usage

1. Navigate to the home page
2. Enter a valid HTTP/HTTPS URL
3. Click "Generate PDF"
4. Wait for processing (automatic status updates)
5. Download your PDF when ready

### Example URLs to Try

- `https://www.google.com`
- `https://github.com`
- `https://stackoverflow.com`
- `https://news.ycombinator.com`

## Technical Details

### Python Service Features

- **Async Processing**: Uses Quart for async request handling
- **Connection Pooling**: Chrome instance pooling for performance
- **Resource Management**: Automatic cleanup of expired instances
- **Queue Management**: Background task processing with queue limits
- **Error Handling**: Comprehensive error tracking and reporting

### Rails App Features

- **Modern UI**: Tailwind CSS with responsive design
- **Real-time Updates**: Auto-refreshing status pages
- **Form Validation**: Client and server-side URL validation
- **Error Handling**: User-friendly error messages
- **Loading States**: Visual feedback during processing

## Development

### Running in Development

1. Start the Python service:
   ```bash
   cd python-service && python main.py
   ```

2. Start the Rails app:
   ```bash
   cd rails-app && PYTHON_SERVICE_URL=http://localhost:5000 rails server
   ```

### Testing

Test the Python service directly:

```bash
curl -X POST http://localhost:5000/generate_pdf \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.google.com"}'
```

Check the status:

```bash
curl http://localhost:5000/pdf_status/YOUR_TASK_ID
```

## Deployment

### Docker Deployment

Use the provided `docker-compose.yml` for easy deployment:

```bash
docker-compose up -d
```

### Deploio Deployment

1. Deploy the Python service as a separate container
2. Deploy the Rails app with `PYTHON_SERVICE_URL` pointing to the Python service
3. Ensure both services can communicate (same network/cluster)

## Performance

The application is designed for high performance:

- **Chrome Instance Pooling**: Reuses browser instances for efficiency
- **Async Processing**: Non-blocking PDF generation
- **Resource Limits**: Automatic cleanup prevents memory leaks
- **Queue Management**: Prevents server overload

## Troubleshooting

### Common Issues

1. **Python service connection errors**
   - Check if the Python service is running
   - Verify the `PYTHON_SERVICE_URL` environment variable
   - Check network connectivity between services

2. **PDF generation failures**
   - Ensure the target URL is accessible
   - Check if the website blocks automated access
   - Verify Chromium installation

3. **Memory issues**
   - The service automatically manages Chrome instances
   - Check Docker memory limits if using containers

### Logs

- Python service logs are written to stdout
- Rails logs are in `rails-app/log/development.log`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - see LICENSE file for details
