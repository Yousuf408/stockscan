FROM python:3.10-slim

RUN apt-get update && apt-get install -y && rm -rf /var/lib/apt/lists/*

WORKDIR /home/user/app
RUN useradd -m -u 1000 user && chown -R user /home/user
USER user

ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH

# Files already here from GitHub Actions push
RUN pip install --no-cache-dir --upgrade -r requirements.txt

EXPOSE 7860
ENV STREAMLIT_SERVER_PORT=7860 STREAMLIT_SERVER_ADDRESS=0.0.0.0

CMD ["streamlit", "run", "app.py"]
