# Internal Architecture

```text
User Input
    │
    ▼
Input Validator
    │
    ▼
Target Classifier
    │
    ├── Domain
    ├── IP
    ├── Email
    ├── Username
    ├── URL
    └── Hash
    │
    ▼
Scan Planner
    │
    ▼
Task Queue
    │
    ▼
Worker Pool
    │
    ▼
OSINT Modules
    │
    ▼
Normalizer
    │
    ▼
Correlation Engine
    │
    ▼
Risk Engine
    │
    ▼
Report Generator
```