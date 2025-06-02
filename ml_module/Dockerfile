FROM python:3.9-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc python3-dev supervisor
COPY requirements.txt .
RUN pip install psycopg2-binary
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py bot.py requirements.txt ./
COPY supervisord.conf /etc/supervisor/conf.d/
# Запуск через supervisor
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]