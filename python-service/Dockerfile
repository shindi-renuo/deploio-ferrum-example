FROM python:3.12

ENV PYPETEER_SKIP_CHROMIUM_DOWNLOAD=true

# Install dependencies
RUN apt-get update && apt-get install -y \
  libasound2 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libc6 \
  libcairo2 \
  libcups2 \
  libdbus-1-3 \
  libexpat1 \
  libfontconfig1 \
  libgcc-s1 \
  libgdk-pixbuf2.0-0 \
  libglib2.0-0 \
  libgtk-3-0 \
  libnspr4 \
  libnss3 \
  libpango-1.0-0 \
  libpangocairo-1.0-0 \
  libx11-xcb1 \
  libxcomposite1 \
  libxdamage1 \
  libxrandr2 \
  xdg-utils \
  libu2f-udev \
  libvulkan1 \
  fonts-liberation \
  ca-certificates \
  wget \
  curl \
  gnupg \
  chromium \
  && rm -rf /var/lib/apt/lists/*

# Create app dir
WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]
