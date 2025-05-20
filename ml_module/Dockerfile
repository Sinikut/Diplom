FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y gcc python3-dev
COPY . .
# Копирование конфига supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
# Запуск через supervisor
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]