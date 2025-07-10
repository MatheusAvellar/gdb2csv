# .GDB to .CSV
A Docker-based converter/exporter of tables in a .GDB file to CSV.

The GDB files I had were from Firebird 1.5.6. If you have a different version, this might not work. Good luck.

![Terminal window displaying the program exporting multiple tables, some with over 10 thousand rows, to CSVs.](/screenshots/1.png)


## Why
I needed one and every single other alternative I tried (and I tried many!) presented me with issues. Yes this one also requires a running Firebird client, but that's what the Docker is for! You shouldn't have to worry about installing it on your precious machine.


## Disclaimers
This worked for me on Windows 11 using [WSL](https://learn.microsoft.com/en-us/windows/wsl/install). If it doesn't work for you, sorry, I can't help you. This project uses [`firebirdsql`](https://github.com/nakagami/pyfirebirdsql/) v0.9.12 (Nov.2015) to connect to the database – meaning neither I, who didn't implement the library, nor the maintainer, who hasn't seen that code in 10 years, can really help you troubleshoot anything. I wish you good luck, and hope this project can save you some hours of research.

For future's sake, I did have trouble using `ALTER TABLE` through the library; but in the end I didn't really need it, so I gave it up. I consider this project a read-only interaction with the file.

The Firebird distribution used – `FirebirdSS-1.5.6.5026-0.nptl.i686.tar.gz` –
was obtained via [SourceForge](https://sourceforge.net/projects/firebird/files/firebird-linux-i386/1.5.6-Release/) under the [Mozilla Public License v1.1](https://www.mozilla.org/en-US/MPL/1.1/). It could be downloaded on the fly during the building stage of the Dockerfile (see comments there), but we're not leaving anything to chance over here.


## How to use
### Setup
When you first download the project, you must build the Docker image. In the
root folder, run:
```sh
docker build -t gdb2csv .
```

Don't forget the trailing `.`!

### Use
Then, whenever you want to export the tables, place your GDB file inside the
`data/` directory and run:
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
does that. Remember to edit in your file and table names!

This will execute the `data/convert.py` file, and should output the listed tables as CSVs inside the `data/` directory. The environment variable `TABLE_LIST` receives a list of semicolon (`;`) separated table names to export.

Alternatively, you can use `TABLE_LIST=all` to convert every table found in the database to CSVs.

By default, the script will export the tables in chunks of 10,000 rows – this is to prevent attempting to load the results of tables with hundreds of thousands of rows into memory with `SELECT *`. If, for any reason, you do not want a chunked export, set the environment variable `NO_CHUNKS`. I didn't really test it, but it should work :)

Note: you do not need to rebuild the Docker image if/when you edit the
`convert.py` file. The `data/` directory is shared as a volume with the Docker
image, so modifications from either you or the image are seen by both.

### Troubleshooting

* `UnicodeDecodeError()`? Try passing a different charset to the `FB_CHARSET` environment variable. By default, it's [Windows-1252](https://en.wikipedia.org/wiki/Windows-1252) (`WIN1252`), but I've had to change it to [Latin 1/ISO-8859-1](https://en.wikipedia.org/wiki/ISO/IEC_8859-1) (`ISO8859_1`) to get it to work at one point. You can see a full list of options [here](https://github.com/nakagami/pyfirebirdsql/blob/59812c2c731bf0f364bc1ab33a46755bc206c05a/firebirdsql/consts.py#L484).


## This sucks
Yeah. I hate that 9 out of 10 solutions out there, including this one, require running a local instance of a decades-old Firebird client. I don't believe anything prevents someone from writing a proper table extractor that uses only the file itself – all the data's in there already!! But alas, no one's paying *me* to do it, so it won't be me. I've seen one (1) extractor that works like that, but it failed to extract most of the data, and the CSVs came with a bunch of empty fields. Perhaps built for a different version of Firebird...

If you do build one, though, let me know and I'll link it here.
