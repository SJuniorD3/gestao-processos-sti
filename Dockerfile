FROM python:3.11-slim

WORKDIR /app

# Copia e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia os arquivos do projeto
COPY . .

# Variáveis padrão
ENV HOST=0.0.0.0
ENV PORT=8080

EXPOSE 8080

CMD ["python", "run.py"]
