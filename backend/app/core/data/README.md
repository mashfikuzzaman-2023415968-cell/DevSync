# Bundled data

`breached-100k.txt.gz` — the public, sorted
"100k most used passwords (NCSC)" list from SecLists
(https://github.com/danielmiessler/SecLists, MIT licence, commit
`21537beae7465102a3ebbedea6a7852a0cbcb3c4`). Used offline by the password policy
(spec §3, §14.4): passwords that appear here (exact or lower-cased) are
rejected. Regenerate deliberately and record the source commit.
