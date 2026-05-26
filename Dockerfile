FROM continuumio/miniconda3:latest

WORKDIR /app

# conda-forge has prebuilt cadquery wheels (pulls in OpenCascade)
RUN conda install -n base -c conda-forge -y python=3.11 cadquery=2.4 \
    && conda clean -afy

# Python deps that aren't on conda-forge in the version we want
RUN pip install --no-cache-dir flask==3.* "anthropic>=0.40" "numpy>=1.24,<2" "scipy>=1.11" "matplotlib>=3.7" "Pillow>=10.0"

# Copy app sources
COPY . /app/

# Bind to 0.0.0.0 on whatever port the host assigns ($PORT). Render sets it
# dynamically; HF Spaces expects 7860; default to 7860 if unset.
ENV HOST=0.0.0.0 PORT=7860 PYTHONUNBUFFERED=1
EXPOSE 7860

CMD ["sh", "-c", "python app.py"]
