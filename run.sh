docker run --rm \
  -v ./data:/data:rw \
  -e FB_GDB_PATH="/data/your_database.gdb" \
  -e FB_USER="SYSDBA" \
  -e FB_PASSWORD="masterkey" \
  -e TABLE_LIST="all" \
  gdb2csv
