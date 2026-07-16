FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Fuentes reales de Microsoft (incluye Times New Roman) para que LibreOffice
# renderice los contratos igual que Word en local, en vez de sustituir por
# Liberation Serif (metric-compatible pero no idéntica, descuadraba las tablas).
RUN sed -i '/^Components:/s/main$/main contrib non-free/' /etc/apt/sources.list.d/debian.sources 2>/dev/null; \
    sed -i '/^deb /s/$/ contrib non-free/' /etc/apt/sources.list 2>/dev/null; \
    echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections && \
    apt-get update && apt-get install -y --no-install-recommends ttf-mscorefonts-installer && \
    fc-cache -f && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
