FROM ubuntu:18.04
# We need Python 3.6.9 and that seemingly locks us to at most Ubuntu 18

SHELL ["/bin/bash", "-c"]
ENV DEBIAN_FRONTEND=noninteractive

################################################################################

# Add 32-bit arch because Firebird 1.5.6 is 32-bit
RUN dpkg --add-architecture i386

# Install what we need; I think this is the bare minimum, but I'm no Docker master
# We need `vim` because the Firebird installer runs `ex`(??)
RUN apt-get update && \
	apt-get install -y --no-install-recommends \
	python3 python3-dev python3-pip python3-gdal gdal-bin \
	locales build-essential \
	libc6:i386 libncurses5:i386 \
	libstdc++5:i386 \
	libfbclient2 \
	vim \
	&& apt-get clean && \
	rm -rf /var/lib/apt/lists/*

# If we use Python >3.6.9, we get a "No module named 'UserDict'" error
# So we limit Ubuntu to 18.04 to get the correct Python version
RUN [[ "$(python3 -V)" != "Python 3.6.9" ]] && \
	echo "$(python3 -V)" && \
	exit 1 \
	|| echo "Correct Python version"

# These could be skipped in theory, but then we get Unicode errors if the
# Python file has any diacritic or non-US characters
RUN echo "LC_ALL=en_US.UTF-8" >> /etc/environment && \
	echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen && \
	echo "LANG=en_US.UTF-8" > /etc/locale.conf
RUN locale-gen en_US.UTF-8

################################################################################

# Upgrade pip and setuptools
RUN pip3 install --upgrade pip setuptools
# Install pandas and limit FBSQL to major version 0 (installs 0.9.12)
# I guess we don't NEED pandas but it makes life easier
RUN pip3 install pandas firebirdsql~=0.0

################################################################################

# Installs Firebird

#  | You can download the .tar.gz on the fly if you want, but then you need to
# \/ trust that SourceForge isn't going anywhere. We're future proofing here.
##RUN wget -O FirebirdSS-1.5.6.5026-0.nptl.i686.tar.gz http://sourceforge.net/projects/firebird/files/firebird-linux-i386/1.5.6-Release/FirebirdSS-1.5.6.5026-0.nptl.i686.tar.gz/download
# Copy local file inside the Docker image instead; if you're downloading,
# comment this out
COPY FirebirdSS-1.5.6.5026-0.nptl.i686.tar.gz FirebirdSS-1.5.6.5026-0.nptl.i686.tar.gz

# The installer is interactive, so we run some `sed`s to remove the questions
RUN tar -zxvf FirebirdSS-1.5.6.5026-0.nptl.i686.tar.gz && \
	cd FirebirdSS-1.5.6.5026-0.i686 && \
	sed -i 's%AskQuestion "Press Enter to start installation or ^C to abort"%%' ./install.sh && \
	sed -i 's%AskQuestion "Please enter new password for SYSDBA user: "%%' ./scripts/postinstall.sh && \
	sed -i 's%NewPasswd=$Answer%NewPasswd=masterkey%' ./scripts/postinstall.sh && \
	./install.sh && \
	cd .. && \
	rm -rf FirebirdSS-1.5.6.5026-0.i686*

# Add to PATH; I don't know if we need this but I don't wanna test it I'm lazy
ENV PATH="/opt/firebird:/opt/firebird/bin:/opt/firebird/lib:$PATH"

################################################################################

# Create /data directory to mirror our real-life one
RUN mkdir -p /data
WORKDIR /data

# Set default environment variables; these can be changed with the run command
ENV FB_GDB_PATH=/data/your_database.gdb
ENV FB_USER=SYSDBA
ENV FB_PASSWORD=masterkey
ENV FB_CHARSET=WIN1252
# Remember that Unicode error thing? We add this as well and it works
ENV PYTHONIOENCODING=utf8

# Set the default command to run when the container starts
# Since we haven't called `firebird start`, we'll need to do it through Python
CMD ["python3", "/data/export.py"]
