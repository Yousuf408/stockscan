FROM python:3.10-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /home/user/app
RUN useradd -m -u 1000 user && chown -R user /home/user
USER user

ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH

RUN pip install --no-cache-dir --upgrade -r requirements.txt streamlit==1.35.0

EXPOSE 7860
ENV STREAMLIT_SERVER_PORT=7860 STREAMLIT_SERVER_ADDRESS=0.0.0.0

CMD ["streamlit", "run", "app.py"]
