FROM python:3.13

# This will likely need to change so we layer into the correct spot in OpenEdX space
RUN mkdir /plugin

WORKDIR /plugin

# Prevents python from writing cache files
ENV PYTHONDONTWRITEBYTECODE=1

# Prevents python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1

# Install and upgrade pip
RUN pip install --upgrade pip

COPY requirements/base.txt /plugin/requirements.txt

# Install dependencies
RUN pip install -r /plugin/requirements.txt

COPY . /plugin




