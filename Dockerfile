# Download all required dependencies and set up the environment for the project
# FROM python:3.11
FROM minizinc/minizinc:2.9.5-jammy

RUN apt-get update
RUN apt-get install -y bc
RUN apt-get install -y python3-pip
RUN pip install --upgrade pip
RUN pip install numpy 
RUN pip install --only-binary=:all: z3-solver  # Only install the binary wheel for z3-solver no compilation needed
RUN pip install mip


# Where the command will be executed
WORKDIR /app

# Copy into WORKDIR
COPY source/ /app

# Command to execute
CMD ["bash", "menu.sh", "--docker"]
