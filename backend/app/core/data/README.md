# Bundled data

`common-passwords.txt.gz` — passwords rejected at registration and password change
(PRD AUTH-002). Built from SecLists `Passwords/Common-Credentials/Pwdb_top-1000000.txt`
(https://github.com/danielmiessler/SecLists, MIT License, Copyright (c) 2018 Daniel
Miessler), keeping only entries of 10–128 printable characters (shorter passwords are
already rejected by the minimum length), lower-cased, de-duplicated and sorted, one per
line, gzip-compressed with mtime 0 so rebuilding the same list gives identical bytes.
