# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the working directory contents into the container at /app
COPY . .

# Default port (can be overridden by the hosting provider)
ENV PORT=8000
EXPOSE $PORT

# Run Chainlit and bind to the PORT environment variable
CMD chainlit run app.py --port $PORT --host 0.0.0.0
