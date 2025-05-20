FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Копируем конфигурацию supervisord
COPY supervisord.conf .
# Запускаем supervisord
CMD ["supervisord"]