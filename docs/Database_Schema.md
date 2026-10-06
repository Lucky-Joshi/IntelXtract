# Database Schema

```text
Targets
--------
id
target
type
created_at

Scans
------
id
target_id
status
started
finished

Findings
---------
id
scan_id
module
severity
confidence
data

Reports
--------
id
scan_id
path
format

Logs
----
id
level
message
timestamp
```