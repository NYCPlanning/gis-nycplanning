
```
.
├─── README.md
├─── environment.yml        --conda env snapshot
├─── pyproject.toml         --package definition
├─── tests.py
├─── .gitignore
├─── docs
│   └─── diagrams
├─── templates
│   ├─── metadata           --XML files
│   └─── issues             --GH issue MD files
├─── utilities              --Misc. tools
│   ├─── powershell
│   ├─── sql
│   └─── python
├─── processes              --main files for each product/process
├─── src
│   └─── dcpgis             --package
│      ├─── __init__.py
│      ├─── logging.py      --module
│      ├─── metadata.py     --module
│      └─── ... 
└─── config                 --config for whole repo
    └─── constants.py
```

Ref:

[Structuring Your Project](https://docs.python-guide.org/writing/structure/)
  