# python:3.12 обязательно — pandas-ta тянет numba, не работающий на 3.13+
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py captions.py chart.py history.py signals.py ./

CMD ["python", "bot.py"]
