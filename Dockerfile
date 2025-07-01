# Используем официальный образ Python
FROM python:3.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем необходимые системные зависимости для PyAV и git (если нужен)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        gcc \
        g++ \
        pkg-config \
        ffmpeg \
        libavdevice-dev \
        libavfilter-dev \
        libavformat-dev \
        libavcodec-dev \
        libavutil-dev \
        libswscale-dev \
        libswresample-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get remove -y git gcc g++ && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Копируем все файлы приложения
COPY . .

# (Опционально) Копируем .env, если он нужен
COPY .env .env

# Открываем порт (FastAPI по умолчанию на 8000)
EXPOSE 8000

# Запускаем приложение через uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
