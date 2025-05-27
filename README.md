# .GDB to .CSV
A Docker-based converter/exporter of tables in a .GDB file to CSV.

The GDB files I had were from Firebird 1.5.6. If you have a different version, this might not work. Good luck.


## Why
I needed one and every single other alternative I tried (and I tried many!) presented me with issues. Yes this one also requires a running Firebird client, but that's what the Docker is for! You shouldn't have to worry about installing it on your precious machine.


## Disclaimers
This worked for me on Windows 11 using [WSL](https://learn.microsoft.com/en-us/windows/wsl/install). If it doesn't work for you, I'm sorry, I can't help you. I wish you good luck, and hope this project can save you some hours of research.

The Firebird distribution used – `FirebirdSS-1.5.6.5026-0.nptl.i686.tar.gz` –
was obtained via [SourceForge](https://sourceforge.net/projects/firebird/files/firebird-linux-i386/1.5.6-Release/) under the [Mozilla Public License v1.1](https://www.mozilla.org/en-US/MPL/1.1/). It could be downloaded on the fly during the building stage of the Dockerfile, but we're not leaving anything to chance over here.


## How to use
In the root folder, run:
```sh
docker build -t gdb2csv .
```

Don't forget the trailing `.`! This will build the Docker image.

Place your GDB file inside the `data/` directory. Then, to export, run:
```sh
docker run --rm \
  -v ./data:/data:rw \
  -e FB_GDB_PATH="/data/your_database.gdb" \
  -e FB_USER="SYSDBA" \
  -e FB_PASSWORD="masterkey" \
  -e TABLE_LIST="table2;table2;table3;table4" \
  gdb2csv
```

If that's too much to remember, there's a convenient `./run.sh` you can run that
does that.

This will execute the `data/convert.py` file, and should output the listed tables as CSVs inside the `data/` directory. The environment variable `TABLE_LIST` receives a list of semicolon (`;`) separated table names to export.

Alternatively, you can use `TABLE_LIST=all` to convert every table found in the database to CSVs.


## This sucks
Yeah. I hate that 9 out of 10 solutions out there, including this one, require running a local instance of a decades-old Firebird client. I don't believe anything prevents someone from writing a proper table extractor that uses only the file itself – all the data's in there already!! But alas, no one's paying *me* to do it, so it won't be me. I've seen one (1) extractor that works like that, but it failed to extract most of the data, and the CSVs came with a bunch of empty fields. Perhaps built for a different version of Firebird...

If you do build one, though, let me know and I'll link it here.
