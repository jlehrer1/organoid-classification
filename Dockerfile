FROM python:3.8-slim-buster

WORKDIR /

ENV PATH="/root/miniconda3/bin:${PATH}"
ARG PATH="/root/miniconda3/bin:${PATH}"
RUN apt-get update

RUN apt-get install -y wget && rm -rf /var/lib/apt/lists/*

RUN wget \
    https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
    && mkdir /root/.conda \
    && bash Miniconda3-latest-Linux-x86_64.sh -b \
    && rm -f Miniconda3-latest-Linux-x86_64.sh \
    conda --version

RUN apt-get --allow-releaseinfo-change update && \
    apt-get install -y --no-install-recommends \
        glances \
        git \
        awscli \
        curl \
        ruby \
        sudo \
        vim \
        libxml-libxml-perl \ 
        time \
        ffmpeg \
        libsm6 \
        libxext6 \
        libgl1-mesa-glx \
        gzip 

RUN conda install --yes boto3 tenacity pandas numpy pip plotly scipy 
RUN conda install -c conda-forge python-kaleido
RUN pip install statdepth==0.7.17 kaleido opencv-python Pillow matplotlib umap-learn dask 

COPY . .