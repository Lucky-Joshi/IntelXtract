# Plugin System

```text
plugins/
├── VirusTotal/
│   ├── plugin.py
│   └── manifest.json
├── Shodan/
│   └── plugin.py
├── Wayback/
│   └── plugin.py
├── SecurityTrails/
│   └── plugin.py
├── Hunter/
│   └── plugin.py
```

Every plugin implements a common interface, for example:

```python
class Plugin:
    name = "Example"

    async def run(self, target):
        ...
```