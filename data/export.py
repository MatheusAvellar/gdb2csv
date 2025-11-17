# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import time
import datetime

import firebirdsql
import pandas as pd


def log(msg):
	current_time = datetime.datetime.now().replace(tzinfo=None)
	print(f"{current_time}| {msg}", flush=True)


def split_array_chunks(data: list, chunk_size: int) -> list:
	output = []
	for i in range(0, len(data), chunk_size):
		output.append(data[i:i + chunk_size])
	return output


def get_connection(db_path: str, user: str="SYSDBA", password: str="masterkey", charset: str="WIN1252"):
	con = None
	# Sometimes we can't connect the first or second times we try,
	# so let's loop it and limit our attempts
	MAX_ATTEMPTS = 20
	attempt = 1
	success = False
	while not success:
		# If we've tried too many times, then give up :\
		if attempt > MAX_ATTEMPTS:
			log("Connection to Firebird failed :(")
			exit(1)
		# Make sure Firebird is running. This command might be run multiple times
		# but it doesn't error out, so it's fine
		subprocess.call(["/etc/init.d/firebird", "start"])

		# We give it a few seconds to start and warm up, we got time
		time.sleep(5)

		# Attempts to connect to Firebird
		try:
			log(f"Attempting connection... {attempt}/{MAX_ATTEMPTS}")
			con = firebirdsql.connect(
				dsn=db_path,
				user=user,
				password=password,
				charset=charset
			)
			log("Connected!")
			success = True
		except firebirdsql.OperationalError as e:
			# Uh oh, we couldn't connect. Don't fret, this happens. We just gotta try
			# again a couple more times to make sure
			log(f"firebirdsql.OperationalError: {e}")
			attempt += 1
		except Exception as e:
			# Something unexpected happened. I don't know what it is. Good luck though
			log(f"Unexpected Exception!")
			log(repr(e))
			attempt += 1

	return con


def execute_query(con, query):
	try:
		cur = con.cursor()
		log(f"Running query:\n{query}")

		START_TIME = time.time()
		cur.execute(query)
		log("Obtaining results...")
		rows = cur.fetchall()
		TOTAL_TIME = time.time() - START_TIME

		log(f"Took {TOTAL_TIME:.1f}s")

		columns = [ desc[0] for desc in cur.description ]
		return (rows, columns)

	# Propagate error back to export_table.. function
	except Exception as e:
		raise e


def probe_table(
	table_name: str,
	chunk_size: int,
	db_path: str,
	user: str="SYSDBA",
	password: str="masterkey",
	charset: str="WIN1252"
):
	con = get_connection(db_path, user=user, password=password, charset=charset)
	# List columns of table
	(rows, _) = execute_query(con, f"""
SELECT RDB$FIELD_NAME
FROM RDB$RELATION_FIELDS
WHERE RDB$RELATION_NAME = '{table_name}'
	""")
	columns = [ row[0] for row in rows ]

	good_cols = []
	bad_cols = []
	log(f"Testing each of the table's {len(columns)} column(s)")
	for column in columns:
		try:
			(rows, _) = execute_query(con, f"""
SELECT FIRST {chunk_size} {column}
FROM {table_name}
ORDER BY RDB$DB_KEY
			""")
			# If we got here, then this column didn't error out;
			# add it to good columns list
			good_cols.append(column)
		except Exception as ex:
			log(f"{repr(ex)}; bad column")
			# Uh oh, we got a bad column! Add it to the list
			bad_cols.append(column)
			# Re-obtain connection in case we lost it
			con = get_connection(db_path, user=user, password=password, charset=charset)

	log(f"Found {len(good_cols)} GOOD column(s) and {len(bad_cols)} BAD column(s)")
	log(f"BAD column(s): {bad_cols}")
	return (good_cols, bad_cols)


def export_table_to_csv(con, table_name: str, max_cols: int = 1_000, columns: list = None):
	log(f"Reading entire table '{table_name}'")

	table_columns = []
	try:
		if not columns:
			# Here we select what columns will be exported at what time
			# See `export_table_to_csv_chunked()` for an explanation
			(rows, _) = execute_query(con, f"""
	SELECT RDB$FIELD_NAME
	FROM RDB$RELATION_FIELDS
	WHERE RDB$RELATION_NAME = '{table_name}'
			""")
			rows = [ row[0] for row in rows ]
			column_count = len(rows)
			log(f"Table has {column_count} column(s)")

			if len(rows) > max_cols:
				table_columns = split_array_chunks(rows, max_cols)
			else:
				table_columns = [ rows ]
		else:
			table_columns = [ columns ]

		for i, column_group in enumerate(table_columns):
			log(f"Attempting to export {len(column_group)} column(s)")
			select_columns = ",".join(column_group) if len(column_group) else "*"

			query = f"""
SELECT {select_columns} FROM {table_name}
			"""
			(rows, columns) = execute_query(con, query)
			df = pd.DataFrame(rows, columns=columns)
			row_count = len(df)
			log(f"Fetched {row_count} rows")

			specifier = "" if i == 0 else f"_cont{i}"
			file_path = f"/data/csv/{table_name}{specifier}.csv"
			# Guarantees /csv directory exists
			os.makedirs(os.path.dirname(file_path), exist_ok=True)
			df.to_csv(file_path, mode='w', header=True, index=False)
			log(f"Saved to '{file_path}'")
			return True

	except firebirdsql.OperationalError as e:
		log(f"OperationalError: {str(e)}; skipping table")
		return False
	# ConnectionResetError, BrokenPipeError, ...
	except Exception as e:
		log(f"{repr(e)}; skipping table")
		return False


def export_table_to_csv_chunked(
	con,
	table_name: str,
	chunk_size: int,
	cont: int = 0,
	max_cols: int = 1_000,
	columns: list = None
):
	log(f"Reading table '{table_name}' in chunks of {chunk_size} rows")
	cont = max(0, int(cont or 0))
	offset = cont
	table_size = None
	table_columns = []
	break_main_loop = False

	# Here, we iterate through the table exporting lines in chunks of `chunk_size`
	# In the first iteration, we attempt to fetch the table's list of columns and
	# its row count. If there's too many columns, we'll split the export into
	# multiple CSVs, otherwise Firebird explodes sometimes
	main_loop_it = -1
	while not break_main_loop:
		main_loop_it += 1
		try:
			if main_loop_it == 0:
				if not columns:
					# Sometimes we get 'OperationalError("Can not recv() packets")'
					# It seems as if that happens when the table has over ~45 columns
					# So, here, we first check how many columns the table has
					(rows, _) = execute_query(con, f"""
	SELECT RDB$FIELD_NAME
	FROM RDB$RELATION_FIELDS
	WHERE RDB$RELATION_NAME = '{table_name}'
					""")
					# `rows` here is [  ( col name, ), ( col name, ), ...  ]
					rows = [ row[0] for row in rows ]  # becomes [ col name, col name, ... ]
					column_count = len(rows)
					log(f"Table has {column_count} column(s)")

					# If we're over the maximum column count
					if len(rows) > max_cols:
						# Split columns into groups of at most limit size
						table_columns = split_array_chunks(rows, max_cols)
					else:
						# Otherwise, pick all columns
						table_columns = [ rows ]
				else:
					table_columns = [ columns ]

				# Get table row count
				(rows, _) = execute_query(con, f"""
SELECT COUNT(*) FROM {table_name}
				""")
				# `rows` is [  ( table_size, )  ]
				table_size = rows[0][0]
				log(f"Table has {table_size} row(s)")

			# Do selective fetching of columns respecting the limit
			# If there's less than the limit, this loop runs only once
			for i, column_group in enumerate(table_columns):
				log(f"Attempting to export {len(column_group)} column(s)")
				select_columns = ",".join(column_group) if len(column_group) else "*"

				# Get chunked results via FIRST N SKIP M syntax using RDB$DB_KEY as a
				# unique representation of each table record
				# [Ref FIRST/SKIP] https://www.firebirdsql.org/refdocs/langrefupd20-select.html#langrefupd20-first-skip
				# [Ref RDB$DB_KEY] https://www.ibphoenix.com/articles/art-00000384
				query = f"""
	SELECT FIRST {chunk_size} SKIP {offset} {select_columns}
	FROM {table_name}
	ORDER BY RDB$DB_KEY
				"""
				(rows, columns) = execute_query(con, query)

				# We could manually write the CSV but we can just use Pandas instead
				df = pd.DataFrame(rows, columns=columns)
				row_count = len(df)
				total_so_far = row_count + offset
				if table_size:
					pct = round((total_so_far/table_size)*100_00)/1_00
					log(f"Fetched {row_count} rows -- ({pct}%) {total_so_far} read of {table_size} total")
				else:
					log(f"Fetched {row_count} rows -- {total_so_far} read")

				specifier = "" if i == 0 else f"_cont{i}"
				file_path = f"/data/csv/{table_name}{specifier}.csv"
				# Create file if it's the first iteration and we're not
				# continuing from a previous export
				if main_loop_it == 0 and cont == 0:
					# Guarantees /csv directory exists
					os.makedirs(os.path.dirname(file_path), exist_ok=True)
					df.to_csv(file_path, mode='w', header=True, index=False)
					log(f"Saved to '{file_path}'")
				else:
					df.to_csv(file_path, mode='a', header=False, index=False)
					log(f"Appended to '{file_path}'")

				# If we fetched no rows (empty table, row count is exact multiple
				# of chunk_size, ...), we're done
				if row_count <= 0:
					log("Fetched no rows; assuming end of table")
					break_main_loop = True
				# If the number of rows fetched is less than chunk_size, we're done
				if row_count < chunk_size:
					log(f"Fetched fewer rows than `chunk_size` ({chunk_size}); assuming end of table")
					break_main_loop = True
			# /for column_group in table_columns

			# Increment offset for the next chunk
			offset += chunk_size

		except firebirdsql.OperationalError as e:
			log(f"OperationalError: {str(e)}; skipping table")
			return False
		except Exception as e:
			log(f"{repr(e)}; skipping table")
			return False
	return True


################################################################################


def main():
	PATH = os.environ.get("FB_GDB_PATH")
	if not os.path.isfile(PATH):
		log(f"FB_GDB_PATH='{PATH}' is not a file!")
		raise ValueError(f"FB_GDB_PATH='{PATH}' is not a file!")

	USER = os.environ.get("FB_USER", "SYSDBA")
	PASS = os.environ.get("FB_PASSWORD", "masterkey")
	# Charset: WIN1252, ISO8859_1, UTF8, ...; see:
	# https://github.com/nakagami/pyfirebirdsql/blob/59812c2c731bf0f364bc1ab33a46755bc206c05a/firebirdsql/consts.py#L484
	# (and https://github.com/nakagami/pyfirebirdsql/commit/5027483b518706c61ab2a1c05c2512e5c03e0a6a)
	CHAR = os.environ.get("FB_CHARSET", "WIN1252")

	TABLE_LIST = os.environ.get("TABLE_LIST", "all")
	NO_CHUNKS = os.environ.get("NO_CHUNKS") is not None
	CONTINUE = int(os.environ.get("CONTINUE", 0))

	CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 10_000))
	MAX_COLUMNS_PER_QUERY = int(os.environ.get("MAX_COLUMNS", 1_000))

	# Attempts connection
	con = get_connection(PATH, user=USER, password=PASS, charset=CHAR)

	# Gets all available tables in the Database
	# [Ref] https://ib-aid.com/download/docs/firebird-language-reference-2.5/fblangref-appx04-relations.html
	(found_tables, _) = execute_query(con, """
SELECT RDB$RELATION_NAME
FROM RDB$RELATIONS
WHERE RDB$SYSTEM_FLAG = 0 AND RDB$VIEW_BLR IS NULL
ORDER BY RDB$RELATION_NAME
	""")

	found_tables = [ row[0] for row in found_tables ]
	print(f"Found {len(found_tables)} table(s):\n" + ", ".join(found_tables))

	wanted_tables = None
	tables_that_exist = None
	# If user wants ALL tables
	if TABLE_LIST.lower() == "all":
		# WE GET THEM ALL
		wanted_tables = found_tables
		tables_that_exist = wanted_tables
	# Otherwise
	else:
		# We split each table name on ';', strip whitespace
		wanted_tables = [ t.strip() for t in TABLE_LIST.split(";") ]
		tables_that_exist = []
		# For every table we found on the database
		for table_name in found_tables:
			# If this is a table we want
			if table_name in wanted_tables:
				# Save it
				tables_that_exist.append(table_name)

	log(f"Found {len(tables_that_exist)} requested tables (out of {len(wanted_tables)} requested, {len(found_tables)} total)\n")

	log("Clearing contents of /data/csv")
	shutil.rmtree("/data/csv", ignore_errors=True)

	# Get metadata -- every column from every table
	export_table_to_csv(con, "RDB$RELATION_FIELDS", max_cols=MAX_COLUMNS_PER_QUERY)

	status = True
	failed_tables = []
	failed_columns = []
	# For every table that exists
	for i, table in enumerate(tables_that_exist):
		log(f"Reading table {i+1}/{len(tables_that_exist)}")

		# If user doesn't want chunks, we just try exporting the entire table
		if NO_CHUNKS:
			status = export_table_to_csv(con, table, max_cols=MAX_COLUMNS_PER_QUERY)
		# Otherwise, we do the more labor-intensive process of chunking the results
		else:
			# For the first table, we might want to continue a previous extraction
			if i == 0:
				if CONTINUE > 0:
					log(f"Continuing previous extraction; skipping {CONTINUE} rows")
				status = export_table_to_csv_chunked(con, table, CHUNK_SIZE, cont=CONTINUE, max_cols=MAX_COLUMNS_PER_QUERY)
			# For the rest of them, start from scratch
			else:
				status = export_table_to_csv_chunked(con, table, CHUNK_SIZE, max_cols=MAX_COLUMNS_PER_QUERY)

		# If Firebird crashed during export
		if not status:
			log("Firebird crashed during export. Probing table columns...")
			# We try exporting 1 row of each column to discover which are broken
			good_cols, bad_cols = probe_table(table, CHUNK_SIZE, PATH, user=USER, password=PASS, charset=CHAR)
			# Save failed table columns as failed
			failed_tables.append(table)
			failed_columns.append("|".join(bad_cols))
			# Get new connection
			con = get_connection(PATH, user=USER, password=PASS, charset=CHAR)
			# Export only non-broken columns
			if NO_CHUNKS:
				status = export_table_to_csv(con, table, columns=good_cols)
			else:
				status = export_table_to_csv_chunked(con, table, CHUNK_SIZE, columns=good_cols)
			if not status:
				# FIXME: it's possible CHUNK_SIZE wasn't enough to find the issue with the column
				# ideally we'd skip only the rows which are problematic, but that might take ages...
				log("Oops :(  skipping table")

		log(f"Done with {table}!\n")
		log("-"*10)

	if len(failed_tables) > 0:
		log("Some table columns were not exported. Saving names to _FAILED_TABLES.csv")
		file_path = f"/data/csv/_FAILED_TABLES.csv"
		# Guarantees /csv directory exists
		os.makedirs(os.path.dirname(file_path), exist_ok=True)
		df = pd.DataFrame.from_dict({ "failed_table": failed_tables, "failed_columns": failed_columns })
		df.to_csv(file_path, mode='w', header=True, index=False)

	con.close()
	return


if __name__ == "__main__":
	main()
