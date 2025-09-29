# Use the same Python base as the main application
FROM python:3.11-slim

# Install the cron daemon
RUN apt-get update && apt-get install -y cron

WORKDIR /app

# Copy requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the ETL script and crontab file
COPY etl_job.py .
COPY crontab .

# Give execution rights on the cron job
RUN chmod 0644 crontab

# Apply the cron job
RUN crontab crontab

# Create the log file to be able to run tail
RUN touch /var/log/cron.log

# Run the command on container startup
# The 'cron -f' command runs cron in the foreground and tail follows the log
CMD sh -c 'cron && tail -f /var/log/cron.log'