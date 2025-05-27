# -*- coding: utf-8 -*-
import os
import subprocess
import time
import sys
import datetime

import firebirdsql
import pandas as pd


def log(msg):
	current_time = datetime.datetime.now().replace(tzinfo=None)
	print(f"{current_time}| {msg}", flush=True)


def get_cursor(db_path, user="SYSDBA", password="masterkey", charset="WIN1252"):
	con = None
	cur = None

	# Sometimes we can't connect the first or second times we try,
	# so let's loop it and limit our attempts
	attempts = 10
	success = False
	while not success:
		# If we've tried too many times, then give up :\
		if attempts <= 0:
			log("Conection to Firebird failed :(")
			exit(1)
		# Make sure Firebird is running. This command might be run multiple times
		# but it doesn't error out, so it's fine
		subprocess.call(["/etc/init.d/firebird", "start"])

		# We give it a few seconds to start and warm up, we got time
		time.sleep(5)

		# Attempts to connect to Firebird
		try:
			log("Attempting connection...")
			con = firebirdsql.connect(
				dsn=db_path,
				user=user,
				password=password,
				charset=charset
			)
			log("Conected! Creating cursor...")
			cur = con.cursor()
			success = True
		except firebirdsql.OperationalError as e:
			# Uh oh, we couldn't connect. Don't fret, this happens. We just gotta try
			# again a couple more times to make sure
			log(f"firebirdsql.OperationalError: {e}")
			attempts -= 1
		except Exception as e:
			# Something unexpected happened. I don't know what it is. Good luck though
			log(f"Unexpected Exception!")
			log(repr(e))
			attempts -= 1

	return (con, cur)


def execute_query(con, cur, query):
	try:
		log(f"Running query:\n{query}")
		cur.execute(query)

		log("Obtaining results...")
		START_TIME = time.time()
		rows = cur.fetchall()
		TOTAL_TIME = time.time() - START_TIME
		log(f"Took {TOTAL_TIME:.1f}s")

		columns = [ desc[0] for desc in cur.description ]
		return (rows, columns)

	except Exception as e:
		log(f"Unexpected Exception!")
		log(repr(e))
		cur.close()
		con.close()
		exit(1)


################################################################################


def main():
	PATH = os.environ.get("FB_GDB_PATH")
	if not os.path.isfile(PATH):
		log(f"FB_GDB_PATH='{PATH}' is not a file!")
		exit(1)

	USER = os.environ.get("FB_USER")
	PASS = os.environ.get("FB_PASSWORD")
	CHAR = os.environ.get("FB_CHARSET", "WIN1252")

	TABLE_LIST = os.environ.get("TABLE_LIST", "all")

	# Attempts connection
	(con, cur) = get_cursor(PATH)

	# Gets all available tables in the Database
	(found_tables, _) = execute_query(con, cur, """
SELECT RDB$RELATION_NAME
FROM RDB$RELATIONS
WHERE RDB$SYSTEM_FLAG = 0 AND RDB$VIEW_BLR IS NULL
ORDER BY RDB$RELATION_NAME
	""")

	wanted_tables = None
	tables_that_exist = None
	# If user wants ALL tables
	if TABLE_LIST.lower() == "all":
		# WE GET THEM ALL
		wanted_tables = [ row[0] for row in found_tables ]
		tables_that_exist = wanted_tables
	# Otherwise
	else:
		# We split each table name on ';', strip whitespace
		wanted_tables = [ t.strip() for t in TABLE_LIST.split(";") ]
		tables_that_exist = []
		# For every table we found on the database
		for table_tuple in found_tables:
			table_name = table_tuple[0]
			# If this is a table we want
			if table_name in wanted_tables:
				# Save it
				tables_that_exist.append(table_name)

	log(f"Found {len(tables_that_exist)} requested tables (out of {len(wanted_tables)} requested, {len(found_tables)} total)\n")

	# For every table that exists
	for i, table in enumerate(tables_that_exist):
		log(f"Reading table {i+1}/{len(tables_that_exist)}")
		# Select everything
		(rows, columns) = execute_query(con, cur, f"SELECT * FROM {table}")

		# We could manually write the CSV but we can just use Pandas instead
		log("Converting to DataFrame...")
		df = pd.DataFrame(rows, columns=columns)

		log("Writing to CSV file...")
		df.to_csv(f"/data/{table}.csv", index=False)
		log("Done!\n")

	cur.close()
	con.close()
	return


if __name__ == "__main__":
	main()
