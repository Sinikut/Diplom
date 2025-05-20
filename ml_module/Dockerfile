FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y gcc python3-dev
COPY . .
# Копируем конфигурацию supervizord
COPY supervizord.conf .
# Запускаем supervisord
CMD ["supervizord"]